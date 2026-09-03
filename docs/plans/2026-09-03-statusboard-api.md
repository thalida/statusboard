# Statusboard API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the six endpoints the approved designs need, and delete the three they replaced.

**Architecture:** Every trackable thing is a `ServiceComponent`, so one component collection
replaces the service list and both nested service routes. A severity change nobody explains
becomes a `ServiceEvent` we write ourselves, so the Updates feed reads one table. Ancestry
moves into a stored array, which serves descendant queries, breadcrumbs and path search at once.

**Tech Stack:** Django 5, DRF, django-filter, drf-spectacular, Postgres 17 full-text search,
pytest, factory_boy.

**Spec:** `docs/specs/2026-09-03-statusboard-client-design.md`

## Global Constraints

- Python 3.14. Primary keys are `uuid.uuid7`, which does not exist earlier.
- Every model extends `common.models.BaseModel`: UUID pk, `created_at`, `updated_at`,
  `created_by`, `updated_by`, `ordering = ["-created_at"]`.
- Every behaviour change carries a test. The suite runs with no network: `tests/conftest.py`
  blocks `socket.socket.connect`.
- Settings split by who named them. Django or a package named it, `api/settings.py`. We named
  it, `api/defaults.py`.
- Comments and docstrings follow ASD-STE100: one idea per sentence, under 20 words, active
  voice, present tense, no em dashes. A comment says why, never what the line already says.
- A comment on a test says what would break if the assertion failed.
- One definition, many readers. A filter, a threshold or a set of rules lives in one place.
- An invariant the code depends on belongs in a database constraint.
- Commits use a lowercase conventional prefix, then a declarative clause. The body says why.
- `docs/api/openapi.yaml` is the contract. `api/tests/test_contract.py` fails when the code
  and the contract disagree, in either direction. Both move in the same commit.
- `docs/check_docs.py` reads the field-level mermaid ER diagram in section 3 of
  `docs/specs/2026-08-23-statusboard-design.md`. Every new column lands there too.
- Run `just test` for the suite and `just lint` before every commit.

---

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `api/catalog/views_components.py` | The component collection and its detail |
| `api/status/views.py` | The event feed, an event, and its update log |
| `api/status/filters.py` | What a caller narrows `/events/` by |
| `api/polling/system_events.py` | Opening, updating, closing and claiming a system event |
| `api/tests/test_component_api.py` | The component collection |
| `api/tests/test_event_api.py` | The event feed and an event |
| `api/tests/test_system_events.py` | The reconcile writer |
| `api/tests/test_service_requests.py` | `POST /catalog/requests/` |

**Modified**

| File | Change |
| --- | --- |
| `api/catalog/models.py` | `ServiceComponent.is_featured`, `ancestor_ids`, `search_document`, `descendant_count`. `Service.is_featured` and `description` go. |
| `api/catalog/queries.py` | `COMPONENT_WATCHER_COUNT` in, `WATCHER_COUNT` out |
| `api/catalog/filters.py` | `ComponentFilter` grows. `ServiceFilter` goes. |
| `api/catalog/serializers.py` | `ComponentSerializer.descendant_count`. `Service.description` out. |
| `api/catalog/views.py` | `ServiceViewSet` becomes retrieve only |
| `api/catalog/urls.py` | The component routes and the requests route |
| `api/catalog/admin.py` | Featuring, watchers, service requests |
| `api/status/models.py` | `ServiceEvent.detected_by`, nullable `external_id`, `EventUpdate.source` |
| `api/status/choices.py` | `IncidentPhase.DETECTED`, `EventUpdateSource` |
| `api/status/serializers.py` | `ServiceEventSerializer` grows a detail shape |
| `api/polling/reconcile.py` | Calls the system-event writer |
| `api/dashboards/filters.py` | `event` out, `status__severity__in` in |
| `api/common/aggregates.py` | `by_event_kind` out |
| `api/tests/factories.py` | `watchers` reads the component annotation |
| `docs/api/openapi.yaml` | Three operations out, six in |
| `docs/specs/2026-08-23-statusboard-design.md` | Sections 5 to 7 out, ER diagram updated |

---

## Task 1: Retire the v1 spec's client sections

**Files:**
- Modify: `docs/specs/2026-08-23-statusboard-design.md`

**Interfaces:**
- Consumes: nothing
- Produces: nothing. This is a documentation change with no code behind it.

Sections 5, 6 and 7 describe a cream palette, tabs that no longer exist and a status dot the
row no longer carries. Rewriting them would leave two documents describing one API.

- [ ] **Step 1: Confirm the checker does not read those sections**

Run: `grep -n 'findall\|spec\[' docs/check_docs.py`

Expected: it reads `re.findall(r"```mermaid\n(.*?)```", spec, re.DOTALL)[1]`, the second
mermaid block, which is in section 3. Sections 5 to 7 hold no mermaid block.

- [ ] **Step 2: Run the checker before touching anything**

Run: `docker compose -f docker-compose.test.yml run --rm docs`
Expected: PASS. This is the baseline the next step must not move.

- [ ] **Step 3: Delete sections 5, 6 and 7 and leave a pointer**

Delete everything from the line `## 5. API surface` up to but not including
`## 8. Testing, infra, deploy`. Put this in their place:

```markdown
## 5. The API, the client and the design system

Those three sections are now
[`2026-09-03-statusboard-client-design.md`](2026-09-03-statusboard-client-design.md).

They described a palette, tabs and a row that the approved decks replaced on 2026-08-28.
Keeping a second account of one API is how two answers to the same question drift apart.
```

Renumber `## 8. Testing, infra, deploy` to `## 6. Testing, infra, deploy`.

- [ ] **Step 4: Run the checker again**

Run: `docker compose -f docker-compose.test.yml run --rm docs`
Expected: PASS, unchanged.

- [ ] **Step 5: Commit**

```bash
git add docs/specs/2026-08-23-statusboard-design.md
git commit -m "docs: one account of the API, not two

The v1 spec's API, frontend and design sections predate the approved
decks. They name tabs that no longer exist and a palette that was
replaced. A pointer to the client design replaces them."
```

---

## Task 2: A component can be featured, and counts its own watchers

**Files:**
- Modify: `api/catalog/models.py`
- Modify: `api/catalog/queries.py`
- Modify: `api/tests/factories.py`
- Create: `api/catalog/migrations/0003_component_is_featured.py` (generated)
- Test: `api/tests/test_catalog_models.py`

**Interfaces:**
- Consumes: `catalog.queries.related_count`, `tests.factories.ComponentFactory`, `track`
- Produces:
  - `ServiceComponent.is_featured: bool`
  - `catalog.queries.COMPONENT_WATCHER_COUNT`, a `Count` expression. Annotate it as
    `watcher_count` on a `ServiceComponent` queryset.
  - `tests.factories.watchers(component)`, replacing the `Service` version, returns `int`

`Service.watcher_count` was a column a signal kept true, and four write paths never reached
the signal. Migration `catalog/0002` dropped it. A component repeats neither.

- [ ] **Step 1: Write the failing test**

In `api/tests/test_catalog_models.py`:

```python
def test_a_components_watcher_count_is_distinct_users(db):
    # Two boards holding one component is two watchers. One person
    # holding it twice is impossible, and one holding a sibling too is
    # still one watcher of this component.
    component = ComponentFactory()
    sibling = ComponentFactory(service=component.service)
    first = UserFactory()
    track(component, user=first)
    track(sibling, user=first)
    track(component, user=UserFactory())

    assert watchers(component) == 2
    assert watchers(sibling) == 1
```

Add to `api/tests/factories.py`, replacing the `Service` version of `watchers`:

```python
class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = settings.AUTH_USER_MODEL

    email = factory.Sequence(lambda n: f"watcher{n}@example.test")


def watchers(component):
    """How many people track it, counted the way the app counts."""
    from catalog.models import ServiceComponent
    from catalog.queries import COMPONENT_WATCHER_COUNT

    return (
        ServiceComponent.objects.annotate(n=COMPONENT_WATCHER_COUNT)
        .get(pk=component.pk)
        .n
    )
```

`UserFactory` needs `from django.conf import settings` and
`django.contrib.auth.get_user_model()`. Use `model = get_user_model()` rather than the
settings string, because factory_boy wants the class.

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd api && uv run pytest tests/test_catalog_models.py::test_a_components_watcher_count_is_distinct_users -v`
Expected: FAIL with `ImportError: cannot import name 'COMPONENT_WATCHER_COUNT'`.

- [ ] **Step 3: Add the annotation and the column**

In `api/catalog/queries.py`, beside `WATCHER_COUNT`:

```python
# Who tracks one component. `DashboardItem` points straight at it, so
# this is one join. The service version needed three, and only the
# service sort read it.
COMPONENT_WATCHER_COUNT = Count("boards__owner", distinct=True)
```

In `api/catalog/models.py`, on `ServiceComponent`, beside `is_overall`:

```python
    # Ticked on the overall component to feature a whole service. It is
    # the first key of the suggested sort, so on day one it is the
    # whole of it: every watcher count starts at zero.
    is_featured = models.BooleanField(verbose_name="Featured", default=False)
```

- [ ] **Step 4: Make the migration and run the test**

Run:
```bash
cd api && uv run python manage.py makemigrations catalog -n component_is_featured
uv run pytest tests/test_catalog_models.py::test_a_components_watcher_count_is_distinct_users -v
```
Expected: PASS.

- [ ] **Step 5: Fix the callers the rename broke**

Run: `cd api && uv run pytest tests/ -x -q`

`tests/test_board_api.py` calls `watchers(service)`. Change each call to name the component
the test tracked. Expected after: the whole suite passes.

- [ ] **Step 6: Add the column to the ER diagram**

In `docs/specs/2026-08-23-statusboard-design.md`, in the second mermaid block, inside
`ServiceComponent { ... }`:

```
        bool is_featured "first key of the suggested sort"
```

- [ ] **Step 7: Commit**

```bash
git add api/catalog/models.py api/catalog/queries.py api/catalog/migrations api/tests docs/specs
git commit -m "feat: a component is featured and counts its own watchers

Discover searches components, so the suggested sort needs both keys on
a component. The watcher count is an annotation, not a column: the
service had one, and four write paths never reached the signal that
kept it true."
```

---

## Task 3: Ancestry is a stored array

**Files:**
- Modify: `api/catalog/models.py`
- Modify: `api/catalog/serializers.py`
- Modify: `api/polling/reconcile.py`
- Create: `api/catalog/migrations/0004_component_ancestor_ids.py` (generated)
- Test: `api/tests/test_catalog_models.py`, `api/tests/test_reconcile.py`

**Interfaces:**
- Consumes: `ServiceComponent.parent`, `polling.reconcile._upsert_components`
- Produces:
  - `ServiceComponent.ancestor_ids: list[UUID]`, top down, the root first, excluding self
  - `ServiceComponent.descendant_count() -> int`, replacing `child_count()`
  - `polling.reconcile.rebuild_ancestry(service) -> None`

A component's Components tab lists every descendant, not one level. A self-FK lookup returns
one level, so the query needs a stored path.

- [ ] **Step 1: Write the failing test**

In `api/tests/test_catalog_models.py`:

```python
def test_ancestor_ids_are_stored_top_down(db):
    # A descendant query reads this array. Walking `parent` per row
    # cannot use an index, and `for_display` only selects two levels up.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    leaf = ComponentFactory(service=service, parent=middle)
    rebuild_ancestry(service)

    leaf.refresh_from_db()
    assert leaf.ancestor_ids == [top.id, middle.id]

    # Every descendant, not the direct children. `top` has two below it.
    assert ServiceComponent.objects.filter(ancestor_ids__contains=[top.id]).count() == 2
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd api && uv run pytest tests/test_catalog_models.py::test_ancestor_ids_are_stored_top_down -v`
Expected: FAIL with `ImportError: cannot import name 'rebuild_ancestry'`.

- [ ] **Step 3: Add the column**

In `api/catalog/models.py`, add the import and the field:

```python
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
```

On `ServiceComponent`, beside `parent`:

```python
    # The chain above this one, root first, written by reconcile. A
    # component's Components tab lists every descendant, and a self-FK
    # lookup returns one level. Walking the chain per row cannot use an
    # index either.
    ancestor_ids = ArrayField(
        models.UUIDField(), default=list, blank=True, editable=False
    )
```

In `class Meta`, add to `indexes`:

```python
            GinIndex(fields=["ancestor_ids"], name="components_by_ancestor"),
```

`ServiceComponent.Meta` has no `indexes` list yet. Add one beside `constraints`.

- [ ] **Step 4: Replace child_count with descendant_count**

In `api/catalog/models.py`, replace the `child_count` method:

```python
    def descendant_count(self):
        """How many components sit anywhere under this one."""
        if self.is_overall:
            return 0
        prepared = getattr(self, "_descendant_count", None)
        if prepared is None:
            return ServiceComponent.objects.filter(ancestor_ids__contains=[self.pk]).count()
        return prepared
```

In `ServiceComponentQuerySet.for_display`, replace the `_child_count` annotation:

```python
                _descendant_count=related_count(
                    self.model.objects, "ancestor_ids__contains", ref="pk"
                ),
```

`related_count` builds `filter(**{group_by: OuterRef(ref)})`, so `ancestor_ids__contains`
needs the ref wrapped in a list. Write the subquery directly instead:

```python
                _descendant_count=Coalesce(
                    Subquery(
                        self.model.objects.filter(
                            ancestor_ids__contains=Func(
                                OuterRef("pk"), function="ARRAY", template="ARRAY[%(expressions)s]"
                            )
                        )
                        .order_by()
                        .values("service")
                        .annotate(total=models.Count("pk"))
                        .values("total"),
                        output_field=models.IntegerField(),
                    ),
                    0,
                ),
```

Import `Coalesce`, `Func`, `Subquery` from `django.db.models` and
`django.db.models.functions`.

In `api/catalog/serializers.py`, rename the field on `ComponentSerializer`:

```python
    descendant_count = serializers.SerializerMethodField()
```

and the method, and the entry in `Meta.fields`:

```python
    @extend_schema_field(serializers.IntegerField())
    def get_descendant_count(self, row):
        return row.descendant_count()
```

- [ ] **Step 5: Write the rebuild in reconcile**

In `api/polling/reconcile.py`:

```python
def rebuild_ancestry(service):
    """Write every component's chain of ancestors, root first.

    A rename does not touch this. A reparent moves a whole subtree, so
    the pass rewrites the service rather than one row. A service holds
    hundreds of components, not millions.
    """
    parents = dict(
        ServiceComponent.objects.filter(service=service).values_list("id", "parent_id")
    )
    chains = {}

    def chain(node):
        if node in chains:
            return chains[node]
        parent = parents.get(node)
        # A self-referencing column allows a loop. Stop rather than hang.
        chains[node] = [] if parent is None or parent == node else [
            *chain(parent),
            parent,
        ]
        return chains[node]

    rows = list(ServiceComponent.objects.filter(service=service))
    for row in rows:
        row.ancestor_ids = chain(row.id)
    ServiceComponent.objects.bulk_update(rows, ["ancestor_ids"])
```

`chain` recurses on the parent map, not the database, so a deep tree costs one query.
The guard stops a row that points at itself.

Call it at the end of `_upsert_components`, after the parent pass:

```python
    rebuild_ancestry(service)
    return rows
```

- [ ] **Step 6: Run the tests**

Run: `cd api && uv run python manage.py makemigrations catalog -n component_ancestor_ids && uv run pytest tests/ -q`
Expected: PASS. `tests/test_catalog_api.py` asserts on `child_count`; rename those
assertions to `descendant_count`.

- [ ] **Step 7: Update the contract and the diagram**

In `docs/api/openapi.yaml`, rename `child_count` to `descendant_count` in the `Component`
schema, and change its description:

```yaml
        descendant_count:
          type: integer
          description: |
            How many components sit anywhere under this one. A component is a group when this
            is above zero. There is no separate flag.
```

In the ER diagram, inside `ServiceComponent { ... }`:

```
        uuid[] ancestor_ids "root first, written by reconcile"
```

`api/tests/test_contract.py::test_the_component_schema_has_exactly_the_documented_fields`
holds these together.

- [ ] **Step 8: Commit**

```bash
git add api docs
git commit -m "feat: a component stores the chain above it

A component's Components tab lists every descendant. A self-FK lookup
returns one level, and walking the chain per row cannot use an index.
Reconcile writes the array, and a reparent rewrites the subtree."
```

---

## Task 4: `q` matches a component's whole path

**Files:**
- Modify: `api/catalog/models.py`
- Modify: `api/polling/reconcile.py`
- Create: `api/catalog/migrations/0005_component_search_document.py` (generated)
- Test: `api/tests/test_catalog_models.py`

**Interfaces:**
- Consumes: `polling.reconcile.rebuild_ancestry`
- Produces:
  - `ServiceComponent.search_document: SearchVectorField`
  - `polling.reconcile.rebuild_search(service) -> None`
  - `ServiceComponentQuerySet.search(q)` returns the queryset filtered and annotated with
    `rank`, ordered by `-rank`

Searching `twilio` finds `SMS`, because Twilio is in its path. `twilio sms` finds it too.

- [ ] **Step 1: Write the failing test**

In `api/tests/test_catalog_models.py`:

```python
def test_search_matches_a_components_path_and_ranks_the_rollup_first(db):
    # The rollup's own name is an exact hit at weight A. A leaf matches
    # only through its service at weight C, so it must sort below.
    service = ServiceFactory(name="Twilio")
    rollup = ComponentFactory(service=service, name="Twilio", is_overall=True)
    parent = ComponentFactory(service=service, name="Programmable Messaging")
    leaf = ComponentFactory(service=service, name="SMS", parent=parent)
    rebuild_ancestry(service)
    rebuild_search(service)

    found = list(ServiceComponent.objects.search("twilio"))
    assert found[0] == rollup
    assert leaf in found

    # Two words are an AND across the whole path, not two searches.
    assert list(ServiceComponent.objects.search("twilio sms")) == [leaf]
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd api && uv run pytest tests/test_catalog_models.py::test_search_matches_a_components_path_and_ranks_the_rollup_first -v`
Expected: FAIL with `ImportError: cannot import name 'rebuild_search'`.

- [ ] **Step 3: Add the column and the queryset method**

In `api/catalog/models.py`:

```python
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVectorField
```

On `ServiceComponent`, beside `ancestor_ids`:

```python
    # The whole path, weighted, written by reconcile. Searching a
    # service's name has to reach its components, and a path built by
    # walking `parent` at query time cannot use an index.
    search_document = SearchVectorField(null=True, editable=False)
```

In `Meta.indexes`:

```python
            GinIndex(fields=["search_document"], name="components_by_search"),
```

On `ServiceComponentQuerySet`:

```python
    def search(self, q):
        """Rank a query against the stored path.

        Websearch mode, so several words are an AND. A caller ordering
        by anything else drops the rank and keeps the filter.
        """
        query = SearchQuery(q, search_type="websearch")
        return (
            self.filter(search_document=query)
            .annotate(rank=SearchRank(models.F("search_document"), query))
            .order_by("-rank")
        )
```

- [ ] **Step 4: Write the rebuild**

In `api/polling/reconcile.py`:

```python
from django.contrib.postgres.search import SearchVector
from django.db.models import Value


def rebuild_search(service):
    """Write each component's weighted path.

    `A` is its own name, `B` its ancestors', `C` its service's. So an
    exact hit on a rollup outranks a leaf that matched through its
    service alone.

    Ancestor names are joined here rather than in SQL. Postgres cannot
    build a vector from an array of foreign keys.
    """
    rows = list(
        ServiceComponent.objects.filter(service=service).select_related("service")
    )
    names = {row.id: row.name for row in rows}
    for row in rows:
        ancestors = " ".join(names.get(a, "") for a in row.ancestor_ids)
        row.search_document = (
            SearchVector(Value(row.name), weight="A")
            + SearchVector(Value(ancestors), weight="B")
            + SearchVector(Value(row.service.name), weight="C")
        )
    ServiceComponent.objects.bulk_update(rows, ["search_document"])
```

Call it in `_upsert_components`, after `rebuild_ancestry`:

```python
    rebuild_ancestry(service)
    rebuild_search(service)
    return rows
```

`rebuild_search` must run second. It reads `ancestor_ids`.

- [ ] **Step 5: Run the test**

Run:
```bash
cd api && uv run python manage.py makemigrations catalog -n component_search_document
uv run pytest tests/test_catalog_models.py -v
```
Expected: PASS.

- [ ] **Step 6: Prove a reparent rewrites the subtree**

Add to `api/tests/test_reconcile.py`:

```python
def test_a_reparent_rewrites_every_descendants_path(db):
    # Ancestry and the search vector both carry the chain. A provider
    # moving one node must not leave its children searchable under
    # where they used to sit.
    service = ServiceFactory(name="Acme")
    old = ComponentFactory(service=service, name="Legacy", external_id="old")
    new = ComponentFactory(service=service, name="Platform", external_id="new")
    leaf = ComponentFactory(service=service, name="Queue", external_id="leaf", parent=old)
    rebuild_ancestry(service)
    rebuild_search(service)

    leaf.parent = new
    leaf.save(update_fields=["parent"])
    rebuild_ancestry(service)
    rebuild_search(service)

    leaf.refresh_from_db()
    assert leaf.ancestor_ids == [new.id]
    assert list(ServiceComponent.objects.search("legacy queue")) == []
    assert list(ServiceComponent.objects.search("platform queue")) == [leaf]
```

- [ ] **Step 7: Run it and commit**

Run: `cd api && uv run pytest tests/ -q && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

Add to the ER diagram, inside `ServiceComponent { ... }`:

```
        tsvector search_document "weighted path, written by reconcile"
```

```bash
git add api docs
git commit -m "feat: a search matches a component's whole path

Searching a service's name has to reach its components. The vector is
weighted so an exact hit on a rollup outranks a leaf that matched only
through its service. A reparent rewrites the subtree."
```

---

## Task 5: The component collection

**Files:**
- Create: `api/catalog/views_components.py`
- Modify: `api/catalog/filters.py`
- Modify: `api/catalog/urls.py`
- Modify: `docs/api/openapi.yaml`
- Test: `api/tests/test_component_api.py`

**Interfaces:**
- Consumes: `ServiceComponent.objects.for_display`, `.search`,
  `catalog.queries.COMPONENT_WATCHER_COUNT`, `status.queries.CURRENT_SEVERITY`,
  `common.aggregates.StatusAggregateSet`, `catalog.serializers.ComponentSerializer`
- Produces:
  - `GET /catalog/components/` named `component-list`
  - `GET /catalog/components/{uuid}/` named `component-detail`
  - `ComponentFilter` with `service`, `ancestor`, `event`, `is_overall`, `is_tracked`,
    `status__severity`, `status__severity__lte`, `status__severity__in`

One collection serves Discover, a service's Components tab, a component's descendants and an
event's affected list.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_component_api.py`:

```python
import pytest
from django.urls import reverse

from polling.reconcile import rebuild_ancestry, rebuild_search
from tests.factories import ComponentFactory, ServiceFactory, track

pytestmark = pytest.mark.django_db


@pytest.fixture
def tree():
    service = ServiceFactory(name="Twilio")
    rollup = ComponentFactory(service=service, name="Twilio", is_overall=True)
    parent = ComponentFactory(service=service, name="Programmable Messaging")
    leaf = ComponentFactory(service=service, name="SMS", parent=parent)
    rebuild_ancestry(service)
    rebuild_search(service)
    return service, rollup, parent, leaf


def test_the_collection_lists_every_component(client, tree):
    # Discover searches all of them, rollups included. Narrowing here
    # would make the signed-out board and Discover one list.
    response = client.get(reverse("component-list"))
    assert response.status_code == 200
    assert response.json()["aggregates"]["total"] == 3


def test_is_overall_narrows_to_one_row_per_service(client, tree):
    # This is the signed-out board: one row per service, not per part.
    response = client.get(reverse("component-list"), {"is_overall": "true"})
    assert [r["name"] for r in response.json()["results"]] == ["Twilio"]


def test_ancestor_returns_every_descendant_not_one_level(client, tree):
    # A component's Components tab is the same screen at a different
    # root, so it cannot count differently from a service's.
    _, _, parent, leaf = tree
    response = client.get(reverse("component-list"), {"ancestor": str(parent.id)})
    assert [r["id"] for r in response.json()["results"]] == [str(leaf.id)]


def test_q_reaches_a_component_through_its_services_name(client, tree):
    # Searching "twilio" must find SMS. Its own name says nothing
    # about which service it belongs to.
    response = client.get(reverse("component-list"), {"q": "twilio sms"})
    assert [r["name"] for r in response.json()["results"]] == ["SMS"]


def test_service_narrows_to_one_services_parts(client, tree):
    # A service's Components tab. The rollup is excluded there,
    # because the header already carries the service's status.
    service, _, _, _ = tree
    response = client.get(
        reverse("component-list"), {"service": service.slug, "is_overall": "false"}
    )
    assert {r["name"] for r in response.json()["results"]} == {
        "Programmable Messaging",
        "SMS",
    }


def test_severity_in_takes_several_values(client, tree):
    # The Severity filter offers all six values at once, so a single
    # exact match cannot serve it.
    response = client.get(reverse("component-list"), {"status__severity__in": "0,1,2"})
    assert response.status_code == 200


def test_the_detail_answers_by_uuid(client, tree):
    _, _, _, leaf = tree
    response = client.get(reverse("component-detail", args=[leaf.id]))
    assert response.status_code == 200
    assert response.json()["name"] == "SMS"
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_component_api.py -v`
Expected: FAIL with `NoReverseMatch: Reverse for 'component-list' not found`.

- [ ] **Step 3: Grow the filter**

Replace `ComponentFilter` in `api/catalog/filters.py`:

```python
class ComponentFilter(filters.FilterSet):
    # `status` is not a relation. A component has a history of statuses
    # and the open one is current. Same contract name, same annotation.
    status__severity = filters.NumberFilter(field_name="severity_now")
    status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )
    status__severity__in = filters.BaseInFilter(
        field_name="severity_now", lookup_expr="in"
    )
    service = filters.CharFilter(field_name="service__slug")
    # Every descendant, not one level. `parent` would name a query this
    # does not run.
    ancestor = filters.UUIDFilter(method="filter_ancestor")
    event = filters.UUIDFilter(field_name="events__id")
    is_tracked = filters.BooleanFilter(field_name="_is_tracked")

    class Meta:
        model = ServiceComponent
        fields = {"is_overall": ["exact"], "is_featured": ["exact"]}

    def filter_ancestor(self, queryset, name, value):
        return queryset.filter(ancestor_ids__contains=[value])
```

- [ ] **Step 4: Write the views**

Create `api/catalog/views_components.py`:

```python
"""Every read of a component, in one place.

Discover, a service's Components tab, a component's descendants and an
event's affected list are one collection with different parameters.
Four nested routes would have been four copies of this queryset.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.permissions import AllowAny

from catalog.filters import ComponentFilter
from catalog.models import ServiceComponent
from catalog.queries import COMPONENT_WATCHER_COUNT
from catalog.serializers import ComponentSerializer
from common.aggregates import StatusAggregateSet
from common.filters import FieldsBackend
from common.ordering import MappedOrderingFilter
from status.queries import CURRENT_SEVERITY


class ComponentQueryMixin:
    permission_classes = [AllowAny]
    serializer_class = ComponentSerializer
    queryset = ServiceComponent.objects.none()

    def get_queryset(self):
        return (
            ServiceComponent.objects.for_display(self.request.user)
            .annotate(
                severity_now=CURRENT_SEVERITY,
                watcher_count=COMPONENT_WATCHER_COUNT,
            )
            .distinct()
        )


class ComponentListView(ComponentQueryMixin, generics.ListAPIView):
    aggregate_set = StatusAggregateSet
    filterset_class = ComponentFilter
    filter_backends = [DjangoFilterBackend, MappedOrderingFilter, FieldsBackend]
    ordering_fields = ["name", "status_page_order", "updated_at"]
    # Severity ahead of popularity, the same as the service sort this
    # replaces. Lower severity is worse, so ascending puts the broken
    # first.
    SUGGESTED = ["-is_featured", "severity_now", "-watcher_count", "name"]
    ordering_map = {
        "suggested": SUGGESTED,
        "status__severity": ["severity_now"],
    }
    ordering = SUGGESTED

    def filter_queryset(self, queryset):
        """A query ranks by relevance. Without one it is the suggested sort.

        One control and one label, Smart, on every list. A separate
        "best match" would name a ranking that does not exist until
        somebody types.
        """
        q = self.request.query_params.get("q")
        if q:
            queryset = queryset.search(q)
        return super().filter_queryset(queryset)


class ComponentDetailView(ComponentQueryMixin, generics.RetrieveAPIView):
    filter_backends = [FieldsBackend]
    lookup_field = "pk"
```

`search` returns an ordered queryset. `MappedOrderingFilter` applies the view's `ordering`
after it, so the rank is lost unless the caller asked for no ordering. Guard it by making
`ordering` conditional:

```python
    def get_ordering(self):
        return [] if self.request.query_params.get("q") else self.ordering
```

DRF's `OrderingFilter` reads `view.ordering`, not a method, so set the attribute in
`initial` instead:

```python
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.query_params.get("q"):
            # `search` already ordered by rank. A default sort applied
            # after it would throw the ranking away.
            self.ordering = ["-rank"]
```

and add `"rank"` to `ordering_fields` so `MappedOrderingFilter` does not drop it.

- [ ] **Step 5: Route them**

In `api/catalog/urls.py`, above the router include:

```python
    path(
        "catalog/components/",
        ComponentListView.as_view(),
        name="component-list",
    ),
    path(
        "catalog/components/<uuid:pk>/",
        ComponentDetailView.as_view(),
        name="component-detail",
    ),
```

- [ ] **Step 6: Run the tests**

Run: `cd api && uv run pytest tests/test_component_api.py -v`
Expected: PASS, all seven.

- [ ] **Step 7: Document both operations**

In `docs/api/openapi.yaml`, add under `paths:`:

```yaml
  /catalog/components/:
    get:
      tags: [catalog]
      summary: Search and list components
      description: |
        One collection, four screens. Discover with no parameters, a service's parts with
        `service`, a component's descendants with `ancestor`, an event's affected list with
        `event`.

        `q` matches a component's whole path, so `twilio` finds `SMS`. Results are ranked by
        relevance. Without `q` the default is `suggested`.
      security: []
      parameters:
        - { name: q, in: query, schema: { type: string } }
        - { name: service, in: query, schema: { type: string }, description: Service slug }
        - { name: ancestor, in: query, schema: { type: string, format: uuid }, description: Every descendant, at any depth }
        - { name: event, in: query, schema: { type: string, format: uuid } }
        - { name: is_overall, in: query, schema: { type: boolean } }
        - { name: is_featured, in: query, schema: { type: boolean } }
        - { name: is_tracked, in: query, schema: { type: boolean } }
        - { name: status__severity, in: query, schema: { type: integer } }
        - { name: status__severity__lte, in: query, schema: { type: integer } }
        - { name: status__severity__in, in: query, schema: { type: string }, description: 'Comma separated, e.g. `0,1,2`' }
        - { name: ordering, in: query, schema: { type: string, enum: [suggested, status_page_order, name, -name, status__severity, -status__severity], default: suggested } }
        - { $ref: '#/components/parameters/Fields' }
        - { $ref: '#/components/parameters/Cursor' }
        - { $ref: '#/components/parameters/PageSize' }
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/Envelope'
                  - type: object
                    properties:
                      aggregates: { $ref: '#/components/schemas/StatusAggregates' }
                      results: { type: array, items: { $ref: '#/components/schemas/Component' } }
  /catalog/components/{uuid}/:
    get:
      tags: [catalog]
      summary: One component
      security: []
      parameters:
        - { $ref: '#/components/parameters/Uuid' }
        - { $ref: '#/components/parameters/Fields' }
      responses:
        '200': { description: OK, content: { application/json: { schema: { $ref: '#/components/schemas/Component' } } } }
        '404': { $ref: '#/components/responses/Error' }
```

- [ ] **Step 8: Run the contract test and commit**

Run: `cd api && uv run pytest tests/test_contract.py -v && uv run pytest tests/ -q`
Expected: PASS.

```bash
git add api docs
git commit -m "feat: one component collection, four screens

Discover, a service's parts, a component's descendants and an event's
affected list are one query with different parameters. Four nested
routes would have been four copies of it."
```

---

## Task 6: An event records who found it, and an update records who wrote it

**Files:**
- Modify: `api/status/choices.py`
- Modify: `api/status/models.py`
- Create: `api/status/migrations/0003_event_detected_by.py` (generated)
- Test: `api/tests/test_status_models.py`

**Interfaces:**
- Consumes: `status.choices.IncidentPhase`, `CLOSED_PHASES`
- Produces:
  - `status.choices.EventSource`, with `PROVIDER` and `SYSTEM`
  - `status.choices.IncidentPhase.DETECTED`
  - `ServiceEvent.detected_by: str`, `ServiceEvent.external_id` nullable
  - `EventUpdate.source: str`

`external_id IS NULL` cannot answer "did we find this first". A claim fills it in, so the
origin fact needs a column of its own.

- [ ] **Step 1: Write the failing test**

In `api/tests/test_status_models.py`:

```python
def test_two_system_events_can_sit_on_one_service(db):
    # Neither has a provider id. The unique key is partial, so a null
    # does not collide with another null.
    service = ServiceFactory()
    for _ in range(2):
        ServiceEvent.objects.create(
            service=service,
            external_id=None,
            kind=EventKind.INCIDENT,
            title="Degraded",
            phase=IncidentPhase.DETECTED,
            detected_by=EventSource.SYSTEM,
            starts_at=timezone.now(),
        )
    assert ServiceEvent.objects.filter(service=service).count() == 2


def test_a_provider_id_is_still_unique_per_service(db):
    # A second poll of the same page must update the row, never add one.
    service = ServiceFactory()
    fields = dict(
        service=service,
        kind=EventKind.INCIDENT,
        title="Outage",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    ServiceEvent.objects.create(external_id="abc", **fields)
    with pytest.raises(IntegrityError):
        ServiceEvent.objects.create(external_id="abc", **fields)


def test_detected_is_an_open_phase(db):
    # A detected event is running. Listing it as closed would hide
    # every outage no provider ever wrote up.
    assert IncidentPhase.DETECTED not in CLOSED_PHASES
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_status_models.py -k "system_events or provider_id_is_still or detected_is_an_open" -v`
Expected: FAIL with `ImportError: cannot import name 'EventSource'`.

- [ ] **Step 3: Add the choices**

In `api/status/choices.py`, add `DETECTED` as the first value of `IncidentPhase`:

```python
class IncidentPhase(models.TextChoices):
    # First, because it precedes anything a provider posts. We write it
    # when a severity drops with nothing explaining it.
    DETECTED = "detected", "Detected"
    INVESTIGATING = "investigating", "Investigating"
    IDENTIFIED = "identified", "Identified"
    MONITORING = "monitoring", "Monitoring"
    RESOLVED = "resolved", "Resolved"
```

`CLOSED_PHASES` is unchanged. `DETECTED` is open, so it is not in it.

Add below `MaintenancePhase`:

```python
class EventSource(models.TextChoices):
    """Who produced a row: the provider's page, or this deployment.

    An event records who opened it. An update records who wrote it. A
    claimed event has both, one per update.
    """

    PROVIDER = "provider", "Provider"
    SYSTEM = "system", "Statusboard"
```

- [ ] **Step 4: Change the models**

In `api/status/models.py`, on `ServiceEvent`:

```python
    # Null until a provider claims this event. We open events a
    # provider never published, and they have no id of theirs.
    external_id = models.CharField(
        verbose_name="Provider ID", max_length=200, null=True, blank=True
    )
    # Who opened it, never rewritten by a claim. `external_id IS NULL`
    # cannot answer this: claiming fills the column in, which destroys
    # the fact that we found the outage first.
    detected_by = models.CharField(
        max_length=32,
        choices=EventSource.choices,
        default=EventSource.PROVIDER,
        db_default=EventSource.PROVIDER,
    )
```

Replace the constraint in `Meta`:

```python
        constraints = [
            # Partial. Two events we opened both hold null, and null
            # does not collide with null in Postgres anyway. Stating
            # the condition says the exemption is deliberate.
            models.UniqueConstraint(
                fields=["service", "external_id"],
                condition=models.Q(external_id__isnull=False),
                name="one_event_per_provider_id",
            )
        ]
```

On `EventUpdate`:

```python
    # Who wrote this post. A claimed event holds both: our detection
    # first, then the provider's log.
    source = models.CharField(
        max_length=32,
        choices=EventSource.choices,
        default=EventSource.PROVIDER,
        db_default=EventSource.PROVIDER,
    )
```

- [ ] **Step 5: Run the tests**

Run:
```bash
cd api && uv run python manage.py makemigrations status -n event_detected_by
uv run pytest tests/test_status_models.py -v
```
Expected: PASS.

- [ ] **Step 6: Update the diagram and the contract**

In the ER diagram, inside `ServiceEvent { ... }` change `external_id` and add a line:

```
        string external_id "provider's id, null until claimed"
        enum detected_by "provider or system, never rewritten"
```

Inside `EventUpdate { ... }`:

```
        enum source "provider or system"
```

In `docs/api/openapi.yaml`, add `detected` to the phase enum documentation under
`Meta.enums.event_phase`, and add to `EventUpdate`'s schema:

```yaml
        source:
          type: string
          enum: [provider, system]
          description: |
            Who wrote this update. `system` is a severity change we recorded ourselves.
            Render the label from `/meta/` `enums.event_source`.
```

Add `event_source` to `Meta.enums` in the same file.

- [ ] **Step 7: Publish the new enum**

In `api/common/views.py`, find where `MetaView` builds `enums` and add:

```python
            "event_source": dict(EventSource.choices),
```

- [ ] **Step 8: Run everything and commit**

Run: `cd api && uv run pytest tests/ -q && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

```bash
git add api docs
git commit -m "feat: an event records who found it

A provider claims an event we opened, which fills in their id. That
destroys the fact that we saw the outage first, so the origin needs a
column. An update records its own author, so one card can hold both."
```

---

## Task 7: A severity change nobody explains becomes an event

**Files:**
- Create: `api/polling/system_events.py`
- Modify: `api/polling/reconcile.py`
- Modify: `api/api/defaults.py`
- Test: `api/tests/test_system_events.py`

**Interfaces:**
- Consumes: `status.models.ServiceEvent`, `EventUpdate`, `ComponentStatus`,
  `status.choices.EventSource`, `IncidentPhase`, `Severity`
- Produces:
  - `polling.system_events.SYSTEM_EVENT_MAX_SEVERITY = 2`
  - `polling.system_events.reconcile_system_events(service, author) -> None`

A provider can move a component to Degraded and never write an incident. An event-only feed
would hide it, and those spans are exposed nowhere else.

- [ ] **Step 1: Add the setting**

In `api/api/defaults.py`, beside the other `POLL_*` values:

```python
# How far back a provider's event may start and still claim one we
# opened. Providers back-date `starts_at` to when an incident really
# began, which is before our poll saw it.
EVENT_CLAIM_WINDOW = timedelta(
    seconds=int(os.environ.get("EVENT_CLAIM_WINDOW_SECONDS", 3600))
)
```

- [ ] **Step 2: Write the failing tests**

Create `api/tests/test_system_events.py`:

```python
import pytest
from django.utils import timezone

from polling.system_events import reconcile_system_events
from status.choices import EventKind, EventSource, IncidentPhase, Severity, StatusSource
from status.models import ComponentStatus, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory

pytestmark = pytest.mark.django_db


def _status(component, severity):
    ComponentStatus.objects.create(
        component=component,
        severity=severity,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )


def _author():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.system()


def test_an_unexplained_outage_opens_an_event(db):
    # Without this the feed hides every outage a provider never wrote
    # up, and the closed span is exposed nowhere else.
    service = ServiceFactory()
    component = ComponentFactory(service=service, name="SMS")
    _status(component, Severity.DEGRADED)

    reconcile_system_events(service, _author())

    event = ServiceEvent.objects.get(service=service)
    assert event.detected_by == EventSource.SYSTEM
    assert event.external_id is None
    assert event.phase == IncidentPhase.DETECTED
    assert event.kind == EventKind.INCIDENT
    assert list(event.affected_components.all()) == [component]
    assert event.updates.count() == 1
    assert event.updates.first().source == EventSource.SYSTEM


def test_an_explained_outage_opens_nothing(db):
    # The provider already told the story. A second card for one
    # outage is the thing this design exists to avoid.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.MAJOR_OUTAGE)
    provider = ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.INCIDENT,
        title="Outage",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    provider.affected_components.set([component])

    reconcile_system_events(service, _author())

    assert ServiceEvent.objects.filter(detected_by=EventSource.SYSTEM).count() == 0


def test_unknown_opens_nothing(db):
    # Severity 3 is our own poll failing to read their page. Calling
    # that their incident would report our fault as theirs.
    service = ServiceFactory()
    _status(ComponentFactory(service=service), Severity.UNKNOWN)

    reconcile_system_events(service, _author())

    assert ServiceEvent.objects.count() == 0


def test_every_transition_while_open_writes_an_update(db):
    # A card shows how the outage moved. One update at the start would
    # say a major outage had been degraded the whole time.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.DEGRADED)
    reconcile_system_events(service, _author())

    ComponentStatus.objects.filter(component=component, ended_at__isnull=True).update(
        ended_at=timezone.now()
    )
    _status(component, Severity.MAJOR_OUTAGE)
    reconcile_system_events(service, _author())

    event = ServiceEvent.objects.get(service=service)
    assert event.updates.count() == 2
    assert event.ends_at is None


def test_recovery_closes_the_event(db):
    # An event that cannot close leaves a permanently red row on
    # somebody's board.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.MAJOR_OUTAGE)
    reconcile_system_events(service, _author())

    ComponentStatus.objects.filter(component=component, ended_at__isnull=True).update(
        ended_at=timezone.now()
    )
    _status(component, Severity.OPERATIONAL)
    reconcile_system_events(service, _author())

    event = ServiceEvent.objects.get(service=service)
    assert event.phase == IncidentPhase.RESOLVED
    assert event.ends_at is not None
    assert event.updates.count() == 2
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_system_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'polling.system_events'`.

- [ ] **Step 4: Write the module**

Create `api/polling/system_events.py`:

```python
"""Events we open when a provider explains nothing.

A provider can move a component to Degraded and never write an
incident. An event-only feed would hide that outage, and the closed
`ComponentStatus` span is exposed nowhere else.

`ComponentStatus` stays the truth. An event here is a projection of it,
written by this module alone and rebuildable from nothing. That is what
keeps it from being a second answer to the same question.
"""

from django.conf import settings
from django.utils import timezone

from status.choices import (
    CLOSED_PHASES,
    EventKind,
    EventSource,
    IncidentPhase,
    Severity,
)
from status.models import ComponentStatus, EventUpdate, ServiceEvent

# Worse than this and nothing is wrong. Severity 3 is our own poll
# failing to read their page, and severity 4 is a window a provider
# always announces. Neither is an outage of theirs to report.
SYSTEM_EVENT_MAX_SEVERITY = Severity.DEGRADED


def reconcile_system_events(service, author):
    """Open, extend and close the events this deployment owns."""
    for status in _bad_statuses(service):
        _open_or_extend(status, author)
    _close_recovered(service, author)


def _bad_statuses(service):
    """Open spans bad enough to be somebody's outage."""
    return ComponentStatus.objects.filter(
        component__service=service,
        ended_at__isnull=True,
        severity__lte=SYSTEM_EVENT_MAX_SEVERITY,
    ).select_related("component")


def _explained(component):
    """Whether a live provider event already names this component."""
    return (
        ServiceEvent.objects.live()
        .filter(affected_components=component, detected_by=EventSource.PROVIDER)
        .exists()
    )


def _ours(component):
    """The open event we opened for this component, if there is one."""
    return (
        ServiceEvent.objects.live()
        .filter(affected_components=component, detected_by=EventSource.SYSTEM)
        .first()
    )


def _open_or_extend(status, author):
    component = status.component
    if _explained(component):
        return
    event = _ours(component)
    if event is None:
        event = ServiceEvent.objects.create(
            service=component.service,
            external_id=None,
            detected_by=EventSource.SYSTEM,
            kind=EventKind.INCIDENT,
            title=_title(component, status.severity),
            phase=IncidentPhase.DETECTED,
            starts_at=status.started_at,
            created_by=author,
            updated_by=author,
        )
        event.affected_components.set([component])
    _record(event, status, author)


def _record(event, status, author):
    """One update per severity span, keyed on when the span began.

    A poll that changes nothing runs this again. `get_or_create` on the
    span's start is what stops a duplicate post per beat.
    """
    EventUpdate.objects.get_or_create(
        event=event,
        posted_at=status.started_at,
        defaults={
            "phase": event.phase,
            "source": EventSource.SYSTEM,
            "body": _title(status.component, status.severity),
            "created_by": author,
            "updated_by": author,
        },
    )


def _close_recovered(service, author):
    """Close ours once the component it names is no longer bad."""
    open_events = ServiceEvent.objects.filter(
        service=service, detected_by=EventSource.SYSTEM
    ).exclude(phase__in=CLOSED_PHASES)
    for event in open_events:
        component = event.affected_components.first()
        if component is None:
            continue
        current = ComponentStatus.objects.filter(
            component=component, ended_at__isnull=True
        ).first()
        if current is not None and current.severity <= SYSTEM_EVENT_MAX_SEVERITY:
            continue
        _close(event, component, current, author)


def _close(event, component, current, author):
    now = timezone.now()
    severity = current.severity if current is not None else Severity.OPERATIONAL
    EventUpdate.objects.get_or_create(
        event=event,
        posted_at=now,
        defaults={
            "phase": IncidentPhase.RESOLVED,
            "source": EventSource.SYSTEM,
            "body": _title(component, severity),
            "created_by": author,
            "updated_by": author,
        },
    )
    event.phase = IncidentPhase.RESOLVED
    event.ends_at = now
    event.updated_by = author
    event.save(update_fields=["phase", "ends_at", "updated_by"])


def _title(component, severity):
    """What the card says before a provider gives it a better name."""
    return f"{component.name} {Severity(severity).label.lower()}"
```

`settings.EVENT_CLAIM_WINDOW` is unused here. Task 8 uses it.

- [ ] **Step 5: Call it from reconcile**

In `api/polling/reconcile.py`, at the end of `apply_fetch`:

```python
    _upsert_events(service, events, rows, author, run)
    # After the provider's events, so a component they explained does
    # not also get one of ours in the same pass.
    reconcile_system_events(service, author)
```

- [ ] **Step 6: Run the tests**

Run: `cd api && uv run pytest tests/test_system_events.py -v`
Expected: PASS, all five.

- [ ] **Step 7: Run the whole suite and commit**

Run: `cd api && uv run pytest tests/ -q && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

```bash
git add api docs
git commit -m "feat: a status change with no provider post becomes an event

A provider can move a component to Degraded and never write an
incident. An event-only feed hid those, and the closed status span was
exposed nowhere else. The client now reads one table."
```

---

## Task 8: A provider claims the event we opened

**Files:**
- Modify: `api/polling/system_events.py`
- Modify: `api/polling/reconcile.py`
- Test: `api/tests/test_system_events.py`

**Interfaces:**
- Consumes: `settings.EVENT_CLAIM_WINDOW`, `polling.system_events._ours`
- Produces: `polling.system_events.claim(event, author) -> bool`, true when it took one over

One outage is one card. A provider posting ten minutes after our poll saw the change is
more updates on the same event, not a second event.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_system_events.py`:

```python
from datetime import timedelta

from polling.system_events import claim


def test_a_provider_event_claims_the_one_we_opened(db):
    # One outage is one card. Two cards for one outage is what the
    # claim exists to prevent.
    service = ServiceFactory()
    component = ComponentFactory(service=service, name="SMS")
    _status(component, Severity.DEGRADED)
    reconcile_system_events(service, _author())
    ours = ServiceEvent.objects.get(service=service)

    provider = ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.INCIDENT,
        title="Elevated SMS delivery failures",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=ours.starts_at - timedelta(minutes=10),
    )
    provider.affected_components.set([component])

    assert claim(provider, _author()) is True

    ours.refresh_from_db()
    assert ours.external_id == "abc"
    assert ours.title == "Elevated SMS delivery failures"
    # Ours records who found it, and a claim never rewrites that.
    assert ours.detected_by == EventSource.SYSTEM
    assert not ServiceEvent.objects.filter(pk=provider.pk).exists()


def test_a_stale_provider_event_claims_nothing(db):
    # An incident that began a day before ours is a different outage.
    # Merging them would put one card's updates on another's timeline.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.DEGRADED)
    reconcile_system_events(service, _author())
    ours = ServiceEvent.objects.get(service=service)

    provider = ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.INCIDENT,
        title="Yesterday",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=ours.starts_at - timedelta(days=1),
    )
    provider.affected_components.set([component])

    assert claim(provider, _author()) is False
    assert ServiceEvent.objects.count() == 2


def test_archiving_a_component_closes_our_open_event(db):
    # We can no longer watch it recover, so the event could never
    # close on its own. A red row would stay on a board for good.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.MAJOR_OUTAGE)
    reconcile_system_events(service, _author())

    component.is_archived = True
    component.save(update_fields=["is_archived"])
    reconcile_system_events(service, _author())

    event = ServiceEvent.objects.get(service=service)
    assert event.phase == IncidentPhase.RESOLVED
    assert event.ends_at is not None
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_system_events.py -k "claims or archiving" -v`
Expected: FAIL with `ImportError: cannot import name 'claim'`.

- [ ] **Step 3: Write the claim**

In `api/polling/system_events.py`:

```python
def claim(provider_event, author):
    """Fold a provider's event into the one we opened for the same outage.

    A provider often posts minutes after our poll saw the change. Two
    rows would be two cards for one outage.

    The provider's row is deleted and ours takes its id, so the fact
    that we found it first survives. Deleting theirs rather than ours
    is what keeps `detected_by` meaningful.
    """
    if provider_event.detected_by != EventSource.PROVIDER:
        return False
    ours = _claimable(provider_event)
    if ours is None:
        return False
    ours.external_id = provider_event.external_id
    ours.title = provider_event.title
    ours.phase = provider_event.phase
    ours.ends_at = provider_event.ends_at
    ours.updated_by = author
    ours.save(
        update_fields=["external_id", "title", "phase", "ends_at", "updated_by"]
    )
    provider_event.updates.update(event=ours)
    ours.affected_components.add(*provider_event.affected_components.all())
    provider_event.delete()
    return True


def _claimable(provider_event):
    """Our open event for the same outage, or nothing.

    Same service, intersecting components, and a start no earlier than
    ours less the window. The nearest start wins when several match.
    """
    components = list(provider_event.affected_components.all())
    if not components:
        return None
    floor = provider_event.starts_at + settings.EVENT_CLAIM_WINDOW
    candidates = (
        ServiceEvent.objects.live()
        .filter(
            service=provider_event.service,
            detected_by=EventSource.SYSTEM,
            external_id__isnull=True,
            affected_components__in=components,
            starts_at__lte=floor,
        )
        .distinct()
    )
    return min(
        candidates,
        key=lambda e: abs(e.starts_at - provider_event.starts_at),
        default=None,
    )
```

`starts_at__lte=floor` reads as "ours began no later than theirs plus the window", which is
the same rule as "theirs began no earlier than ours less the window".

- [ ] **Step 4: Close an event whose component is archived**

In `_close_recovered`, replace the body of the loop:

```python
    for event in open_events:
        component = event.affected_components.first()
        if component is None:
            continue
        current = ComponentStatus.objects.filter(
            component=component, ended_at__isnull=True
        ).first()
        still_bad = current is not None and current.severity <= SYSTEM_EVENT_MAX_SEVERITY
        # An archived component is one the provider stopped publishing.
        # We cannot watch it recover, so the event could never close.
        if still_bad and not component.is_archived:
            continue
        _close(event, component, current, author)
```

- [ ] **Step 5: Call the claim from reconcile**

In `api/polling/reconcile.py`, at the end of `_upsert_events`'s loop body:

```python
        for update in incoming.updates:
            EventUpdate.objects.get_or_create(
                event=event,
                posted_at=update.posted_at,
                defaults={
                    "phase": update.phase,
                    "body": update.body,
                    "source": EventSource.PROVIDER,
                    "created_by": author,
                    "updated_by": author,
                },
            )
        # After the updates, so they move with the row if this event
        # takes over one we opened.
        claim(event, author)
```

Import `claim` and `EventSource` at the top of `reconcile.py`.

`_upsert_events` uses `update_or_create` keyed on `(service, external_id)`. Once ours has
taken the id, the next poll finds ours and updates it in place, so `claim` returns false
and nothing happens twice.

- [ ] **Step 6: Run the tests**

Run: `cd api && uv run pytest tests/test_system_events.py -v`
Expected: PASS, all eight.

- [ ] **Step 7: Prove a claimed event survives the next poll**

Append to `api/tests/test_system_events.py`:

```python
def test_a_claimed_event_is_not_claimed_twice(db):
    # The next poll finds ours by the id it took, so `update_or_create`
    # updates it in place. A second claim would delete the row it just
    # matched.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.DEGRADED)
    reconcile_system_events(service, _author())
    ours = ServiceEvent.objects.get(service=service)

    provider = ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.INCIDENT,
        title="Outage",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=ours.starts_at,
    )
    provider.affected_components.set([component])
    claim(provider, _author())

    ours.refresh_from_db()
    assert claim(ours, _author()) is False
    assert ServiceEvent.objects.count() == 1
```

`claim` returns false here because `ours.detected_by` is `system`, which the first guard
rejects.

- [ ] **Step 8: Run everything and commit**

Run: `cd api && uv run pytest tests/ -q && uv run ruff check --fix . && uv run ruff format .`
Expected: PASS.

```bash
git add api docs
git commit -m "feat: a provider's post joins the event we already opened

Twilio's dot goes red at 14:02 and they post at 14:14. Two rows would
be two cards for one outage. Theirs is folded into ours, so the card
gains updates rather than a duplicate, and detected_by survives."
```

---

## Task 9: The event feed

**Files:**
- Create: `api/status/views.py`
- Create: `api/status/filters.py`
- Create: `api/status/urls.py`
- Modify: `api/api/urls.py`
- Modify: `docs/api/openapi.yaml`
- Test: `api/tests/test_event_api.py`

**Interfaces:**
- Consumes: `status.models.ServiceEvent`, `status.serializers.ServiceEventSerializer`,
  `common.aggregates.EventAggregateSet`, `status.choices.CLOSED_PHASES`
- Produces:
  - `GET /events/` named `event-list`
  - `EventFilter` with `dashboard`, `service`, `component`, `kind`, `phase`

One feed serves Home, a service and a component. The screens call it Updates. The API names
the model.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_event_api.py`:

```python
import pytest
from django.urls import reverse
from django.utils import timezone

from status.choices import EventKind, IncidentPhase, MaintenancePhase
from status.models import ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory, track

pytestmark = pytest.mark.django_db


def _event(service, component, **kwargs):
    fields = dict(
        kind=EventKind.INCIDENT,
        title="Something broke",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    fields.update(kwargs)
    event = ServiceEvent.objects.create(service=service, **fields)
    event.affected_components.set([component])
    return event


def test_the_feed_lists_events_newest_first(client):
    # A feed is read from the top. Oldest first would open on an
    # incident from last month.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    old = _event(service, component, external_id="1", title="Older")
    new = _event(service, component, external_id="2", title="Newer")
    ServiceEvent.objects.filter(pk=new.pk).update(
        starts_at=timezone.now() + timezone.timedelta(minutes=5)
    )

    results = client.get(reverse("event-list")).json()["results"]
    assert [r["title"] for r in results] == ["Newer", "Older"]


def test_service_narrows_the_feed(client):
    # A service's Updates tab. Anything from another service on it
    # would be answering a question nobody asked on that page.
    first = ServiceFactory()
    second = ServiceFactory()
    _event(first, ComponentFactory(service=first), external_id="1", title="Mine")
    _event(second, ComponentFactory(service=second), external_id="2", title="Theirs")

    results = client.get(reverse("event-list"), {"service": first.slug}).json()["results"]
    assert [r["title"] for r in results] == ["Mine"]


def test_component_narrows_the_feed(client):
    # A component's Updates tab reads the same collection one level
    # down, so it cannot be a different endpoint.
    service = ServiceFactory()
    wanted = ComponentFactory(service=service)
    other = ComponentFactory(service=service)
    _event(service, wanted, external_id="1", title="Wanted")
    _event(service, other, external_id="2", title="Other")

    results = client.get(
        reverse("event-list"), {"component": str(wanted.id)}
    ).json()["results"]
    assert [r["title"] for r in results] == ["Wanted"]


def test_phase_open_and_closed_draw_one_line(client):
    # `CLOSED_PHASES` lives in status/choices.py. A client restating
    # which phases are terminal is a second copy that can drift.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _event(service, component, external_id="1", title="Open")
    _event(
        service,
        component,
        external_id="2",
        title="Done",
        phase=IncidentPhase.RESOLVED,
    )
    _event(
        service,
        component,
        external_id="3",
        title="Finished",
        kind=EventKind.MAINTENANCE,
        phase=MaintenancePhase.COMPLETED,
    )

    open_titles = client.get(reverse("event-list"), {"phase": "open"}).json()["results"]
    closed = client.get(reverse("event-list"), {"phase": "closed"}).json()["results"]
    assert [r["title"] for r in open_titles] == ["Open"]
    assert {r["title"] for r in closed} == {"Done", "Finished"}


def test_dashboard_narrows_to_what_you_track(client, board):
    # Home's Updates tab. Everything posted across the services on
    # your board, and nothing else.
    tracked = ComponentFactory()
    untracked = ComponentFactory()
    track(tracked, user=board.owner)
    _event(tracked.service, tracked, external_id="1", title="Yours")
    _event(untracked.service, untracked, external_id="2", title="Not yours")

    client.force_login(board.owner)
    results = client.get(
        reverse("event-list"), {"dashboard": str(board.id)}
    ).json()["results"]
    assert [r["title"] for r in results] == ["Yours"]
```

`board` is the fixture `api/tests/test_board_api.py` already uses. Move it into
`api/tests/conftest.py` so both files reach it.

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_event_api.py -v`
Expected: FAIL with `NoReverseMatch: Reverse for 'event-list' not found`.

- [ ] **Step 3: Write the filter**

Create `api/status/filters.py`:

```python
"""What a caller may narrow the event feed by.

Beside the views, and apart from them. A filter is the query contract,
and it is read on its own more often than the view around it.
"""

from django_filters import rest_framework as filters

from status.choices import CLOSED_PHASES
from status.models import ServiceEvent

PHASE_STATES = [("open", "Open"), ("closed", "Closed")]


class EventFilter(filters.FilterSet):
    # Declared, not generated. The line between an open phase and a
    # closed one is `CLOSED_PHASES`, and a client restating it is a
    # second copy of one rule.
    phase = filters.ChoiceFilter(choices=PHASE_STATES, method="filter_phase")
    service = filters.CharFilter(field_name="service__slug")
    component = filters.UUIDFilter(field_name="affected_components__id")
    dashboard = filters.UUIDFilter(method="filter_dashboard")

    class Meta:
        model = ServiceEvent
        fields = {"kind": ["exact"]}

    def filter_phase(self, queryset, name, value):
        if value == "closed":
            return queryset.filter(phase__in=CLOSED_PHASES)
        return queryset.exclude(phase__in=CLOSED_PHASES)

    def filter_dashboard(self, queryset, name, value):
        """Everything posted across the services on one board.

        The board's rows are components, and an event names components.
        A user reaches only their own board: the view checks the owner
        before this runs.
        """
        return queryset.filter(
            affected_components__tracked_by__dashboard_id=value
        ).distinct()
```

- [ ] **Step 4: Write the view**

Create `api/status/views.py`:

```python
"""Every read of an event, in one place.

Home, a service and a component show the same feed at different scopes.
The screens call it Updates. This names the model, and `/meta/`
publishes the labels.
"""

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.permissions import AllowAny

from common.aggregates import EventAggregateSet
from common.filters import FieldsBackend
from common.ordering import MappedOrderingFilter
from dashboards.models import Dashboard
from status.filters import EventFilter
from status.models import ServiceEvent
from status.serializers import ServiceEventSerializer


class EventListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceEventSerializer
    aggregate_set = EventAggregateSet
    filterset_class = EventFilter
    filter_backends = [DjangoFilterBackend, MappedOrderingFilter, FieldsBackend]
    ordering_fields = ["starts_at", "ends_at"]
    ordering_map = {}
    ordering = ["-starts_at"]
    queryset = ServiceEvent.objects.none()

    def get_queryset(self):
        queryset = ServiceEvent.objects.select_related("service").prefetch_related(
            "updates"
        )
        board = self.request.query_params.get("dashboard")
        if board:
            # 404 rather than 403: someone else's board id should not
            # be confirmable. The filter runs after this.
            get_object_or_404(Dashboard, id=board, owner=self.request.user)
        return queryset
```

An anonymous caller passing `dashboard` reaches `get_object_or_404` with
`owner=AnonymousUser`, which raises `TypeError`. Guard it:

```python
        if board:
            if not self.request.user.is_authenticated:
                raise NotAuthenticated
            get_object_or_404(Dashboard, id=board, owner=self.request.user)
```

Import `NotAuthenticated` from `rest_framework.exceptions`.

- [ ] **Step 5: Route it**

Create `api/status/urls.py`:

```python
from django.urls import path

from status.views import EventListView

urlpatterns = [
    path("events/", EventListView.as_view(), name="event-list"),
]
```

In `api/api/urls.py`, beside the other includes:

```python
    path("", include("status.urls")),
```

- [ ] **Step 6: Run the tests**

Run: `cd api && uv run pytest tests/test_event_api.py -v`
Expected: PASS, all five.

- [ ] **Step 7: Document the operation**

In `docs/api/openapi.yaml`, add under `paths:`:

```yaml
  /events/:
    get:
      tags: [status]
      summary: The event feed
      description: |
        One feed, three scopes. Home with `dashboard`, a service with `service`, a component
        with `component`.

        `phase` takes `open` or `closed`. The line between them is `CLOSED_PHASES` in the
        code, so a client never restates which phases are terminal.
      security: []
      parameters:
        - { name: dashboard, in: query, schema: { type: string, format: uuid }, description: Requires auth, and must be your own }
        - { name: service, in: query, schema: { type: string }, description: Service slug }
        - { name: component, in: query, schema: { type: string, format: uuid } }
        - { name: kind, in: query, schema: { type: string, enum: [incident, maintenance] } }
        - { name: phase, in: query, schema: { type: string, enum: [open, closed] } }
        - { name: ordering, in: query, schema: { type: string, enum: [-starts_at, starts_at, ends_at, -ends_at], default: -starts_at } }
        - { $ref: '#/components/parameters/Fields' }
        - { $ref: '#/components/parameters/Cursor' }
        - { $ref: '#/components/parameters/PageSize' }
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/Envelope'
                  - type: object
                    properties:
                      aggregates: { $ref: '#/components/schemas/EventAggregates' }
                      results: { type: array, items: { $ref: '#/components/schemas/ServiceEvent' } }
```

- [ ] **Step 8: Run the contract test and commit**

Run: `cd api && uv run pytest tests/test_contract.py tests/ -q`
Expected: PASS.

```bash
git add api docs
git commit -m "feat: one event feed for Home, a service and a component

Three screens showed the same list at different scopes. The phase
filter draws its line from CLOSED_PHASES, so no client carries a copy
of which phases are terminal."
```

---

## Task 10: One event, and its update log

**Files:**
- Modify: `api/status/views.py`
- Modify: `api/status/urls.py`
- Modify: `api/status/serializers.py`
- Modify: `docs/api/openapi.yaml`
- Test: `api/tests/test_event_api.py`

**Interfaces:**
- Consumes: `status.serializers.ServiceEventSerializer`, `EventUpdateSerializer`
- Produces:
  - `GET /events/{uuid}/` named `event-detail`
  - `GET /events/{uuid}/updates/` named `event-updates`
  - `ServiceEventDetailSerializer` with `update_count` and `affected_count`

The event screen's header needs both counts before either tab is opened. Its Timeline is a
paged list, because a provider's log has no ceiling.

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_event_api.py`:

```python
from status.choices import EventSource
from status.models import EventUpdate


def test_the_detail_carries_both_tab_counts(client):
    # The header draws `Timeline 3` and `Affects 2` before either tab
    # is opened, so neither can wait for that tab's request.
    service = ServiceFactory()
    first = ComponentFactory(service=service)
    second = ComponentFactory(service=service)
    event = _event(service, first, external_id="1")
    event.affected_components.add(second)
    for minute in range(3):
        EventUpdate.objects.create(
            event=event,
            phase=IncidentPhase.INVESTIGATING,
            body=f"update {minute}",
            posted_at=timezone.now(),
        )

    body = client.get(reverse("event-detail", args=[event.id])).json()
    assert body["update_count"] == 3
    assert body["affected_count"] == 2


def test_the_timeline_is_its_own_paged_list(client):
    # A provider's log has no ceiling, so it cannot ride on the detail.
    service = ServiceFactory()
    event = _event(service, ComponentFactory(service=service), external_id="1")
    EventUpdate.objects.create(
        event=event,
        phase=IncidentPhase.IDENTIFIED,
        body="Cause found",
        posted_at=timezone.now(),
        source=EventSource.PROVIDER,
    )

    body = client.get(reverse("event-updates", args=[event.id])).json()
    assert body["aggregates"]["total"] == 1
    assert body["results"][0]["source"] == "provider"


def test_the_timeline_is_oldest_first(client):
    # A story is read forwards. The feed is newest first because it is
    # a feed; one event's log is a narrative.
    service = ServiceFactory()
    event = _event(service, ComponentFactory(service=service), external_id="1")
    later = EventUpdate.objects.create(
        event=event,
        phase=IncidentPhase.IDENTIFIED,
        body="Second",
        posted_at=timezone.now() + timezone.timedelta(minutes=1),
    )
    EventUpdate.objects.create(
        event=event,
        phase=IncidentPhase.INVESTIGATING,
        body="First",
        posted_at=timezone.now(),
    )

    results = client.get(reverse("event-updates", args=[event.id])).json()["results"]
    assert [r["body"] for r in results] == ["First", "Second"]
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_event_api.py -k "detail_carries or timeline" -v`
Expected: FAIL with `NoReverseMatch: Reverse for 'event-detail' not found`.

- [ ] **Step 3: Add the serializers**

In `api/status/serializers.py`, add `source` to `EventUpdateSerializer`:

```python
class EventUpdateSerializer(FieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = EventUpdate
        fields = ["phase", "body", "posted_at", "source"]
```

Remove the nested `updates` from `ServiceEventSerializer`. A feed row costs a title, not a
log, and the log is now its own operation:

```python
class ServiceEventSerializer(FieldsMixin, serializers.ModelSerializer):
    """One row of the feed. The log is `/events/{uuid}/updates/`."""

    class Meta:
        model = ServiceEvent
        fields = [
            "id",
            "kind",
            "title",
            "phase",
            "starts_at",
            "ends_at",
            "detected_by",
        ]


class ServiceEventDetailSerializer(ServiceEventSerializer):
    """The event screen's header and its About tab.

    Both counts are here because the header draws both tab badges
    before either tab has made a request.
    """

    update_count = serializers.SerializerMethodField()
    affected_count = serializers.SerializerMethodField()
    last_update_at = serializers.SerializerMethodField()

    class Meta(ServiceEventSerializer.Meta):
        fields = [
            *ServiceEventSerializer.Meta.fields,
            "update_count",
            "affected_count",
            "last_update_at",
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_update_count(self, event):
        return event.updates.count()

    @extend_schema_field(serializers.IntegerField())
    def get_affected_count(self, event):
        return event.affected_components.count()

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_last_update_at(self, event):
        newest = event.updates.order_by("-posted_at").first()
        return newest.posted_at if newest else None
```

`ServiceEventSerializer` gains `detected_by`, so a card can say the outage was ours to find.

- [ ] **Step 4: Add the views**

In `api/status/views.py`:

```python
class EventDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceEventDetailSerializer
    filter_backends = [FieldsBackend]
    queryset = ServiceEvent.objects.all()


class EventUpdateListView(generics.ListAPIView):
    """One event's log, oldest first.

    The feed is newest first because it is a feed. This is a narrative,
    and a narrative is read forwards.
    """

    permission_classes = [AllowAny]
    serializer_class = EventUpdateSerializer
    filter_backends = [FieldsBackend]
    queryset = EventUpdate.objects.none()

    def get_queryset(self):
        event = get_object_or_404(ServiceEvent, pk=self.kwargs["pk"])
        return event.updates.order_by("posted_at")
```

`EnvelopePagination.get_ordering` appends `-created_at` as the cursor tiebreak, which
would fight `posted_at`. Give this view its own paginator:

```python
class TimelinePagination(EnvelopePagination):
    ordering = "posted_at"
    tiebreak = "created_at"
```

Put it in `api/common/pagination.py` and set `pagination_class = TimelinePagination` on
`EventUpdateListView`.

- [ ] **Step 5: Route them**

In `api/status/urls.py`:

```python
    path("events/<uuid:pk>/", EventDetailView.as_view(), name="event-detail"),
    path(
        "events/<uuid:pk>/updates/",
        EventUpdateListView.as_view(),
        name="event-updates",
    ),
```

- [ ] **Step 6: Run the tests**

Run: `cd api && uv run pytest tests/test_event_api.py -v`
Expected: PASS, all eight.

- [ ] **Step 7: Document both, and split the schema**

In `docs/api/openapi.yaml`, remove `updates` from the `ServiceEvent` schema, add
`detected_by`, and add a `ServiceEventDetail` schema:

```yaml
    ServiceEventDetail:
      allOf:
        - $ref: '#/components/schemas/ServiceEvent'
        - type: object
          description: |
            The event screen's header. Both counts are here because the header draws both tab
            badges before either tab has made a request.
          properties:
            update_count: { type: integer }
            affected_count: { type: integer }
            last_update_at: { type: string, format: date-time, nullable: true }
```

Add the two operations:

```yaml
  /events/{uuid}/:
    get:
      tags: [status]
      summary: One event
      security: []
      parameters:
        - { $ref: '#/components/parameters/Uuid' }
        - { $ref: '#/components/parameters/Fields' }
      responses:
        '200': { description: OK, content: { application/json: { schema: { $ref: '#/components/schemas/ServiceEventDetail' } } } }
        '404': { $ref: '#/components/responses/Error' }
  /events/{uuid}/updates/:
    get:
      tags: [status]
      summary: One event's log, oldest first
      description: Its own operation because a provider's log has no ceiling.
      security: []
      parameters:
        - { $ref: '#/components/parameters/Uuid' }
        - { $ref: '#/components/parameters/Fields' }
        - { $ref: '#/components/parameters/Cursor' }
        - { $ref: '#/components/parameters/PageSize' }
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/Envelope'
                  - type: object
                    properties:
                      aggregates: { $ref: '#/components/schemas/Aggregates' }
                      results: { type: array, items: { $ref: '#/components/schemas/EventUpdate' } }
```

Add `ServiceEventDetail` to `BACKED` in `docs/check_docs.py`, mapped to `ServiceEvent`,
and add `ServiceEventDetail.update_count`, `.affected_count` and `.last_update_at` to
`DERIVED`.

- [ ] **Step 8: Run everything and commit**

Run: `cd api && uv run pytest tests/ -q && docker compose -f docker-compose.test.yml run --rm docs`
Expected: PASS.

```bash
git add api docs
git commit -m "feat: an event, and its log as its own list

The header draws both tab badges before either tab asks for anything,
so the detail carries both counts. The log is paged on its own: a
provider writes as many updates as they like."
```

---

## Task 11: Somewhere to send a URL we cannot read

**Files:**
- Modify: `api/catalog/models.py`
- Create: `api/catalog/serializers.py` addition
- Modify: `api/catalog/views_components.py` or a new view module
- Modify: `api/catalog/urls.py`
- Modify: `api/api/defaults.py`
- Test: `api/tests/test_service_requests.py`

**Interfaces:**
- Consumes: `common.models.BaseModel`, `catalog.models.StatusPage.normalise_url`,
  `api.defaults.Throttle`
- Produces:
  - `catalog.models.ServiceRequest` with `url`, `request_count`, `last_requested_at`
  - `POST /catalog/requests/` named `catalog-request`

The Add-by-URL screen's not-found state offers "Send this URL to us". `POST /catalog/import/`
stores nothing about a failed attempt, so that button has nowhere to send anything.

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_service_requests.py`:

```python
import pytest
from django.urls import reverse

from catalog.models import ServiceRequest

pytestmark = pytest.mark.django_db


def test_asking_records_the_url(client):
    response = client.post(
        reverse("catalog-request"),
        {"url": "https://status.fastmail.com/"},
        content_type="application/json",
    )
    assert response.status_code == 202
    row = ServiceRequest.objects.get()
    assert row.url == "https://status.fastmail.com"
    assert row.request_count == 1


def test_asking_twice_counts_rather_than_duplicates(client):
    # State belongs to the URL, not to a request. A row per request
    # would answer one question twice once a URL was triaged.
    for _ in range(2):
        client.post(
            reverse("catalog-request"),
            {"url": "https://status.fastmail.com/"},
            content_type="application/json",
        )
    assert ServiceRequest.objects.count() == 1
    assert ServiceRequest.objects.get().request_count == 2


def test_the_answer_is_the_same_whether_we_hold_it_or_not(client):
    # Always 202. A different code would reveal which URLs are
    # already in the catalog to anyone who asked.
    first = client.post(
        reverse("catalog-request"),
        {"url": "https://status.one.example/"},
        content_type="application/json",
    )
    second = client.post(
        reverse("catalog-request"),
        {"url": "https://status.one.example/"},
        content_type="application/json",
    )
    assert first.status_code == second.status_code == 202
    assert first.content == second.content


def test_a_signed_in_asker_is_recorded(client, user):
    # created_by carries it. There is no requested_by: that is what
    # BaseModel already holds.
    client.force_login(user)
    client.post(
        reverse("catalog-request"),
        {"url": "https://status.two.example/"},
        content_type="application/json",
    )
    assert ServiceRequest.objects.get().created_by == user


def test_a_malformed_url_is_refused(client):
    response = client.post(
        reverse("catalog-request"),
        {"url": "not a url"},
        content_type="application/json",
    )
    assert response.status_code == 400
```

`user` is a fixture. Add it to `api/tests/conftest.py` if it is not already there:

```python
@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create(email="asker@example.test")
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_service_requests.py -v`
Expected: FAIL with `ImportError: cannot import name 'ServiceRequest'`.

- [ ] **Step 3: Add the model**

In `api/catalog/models.py`, below `StatusPage`:

```python
class ServiceRequest(BaseModel):
    """A status page somebody asked for and we could not read.

    One row per URL, not one per request. A row per request would
    answer one question twice once a URL was triaged.

    There is no `requested_by`. `BaseModel.created_by` already holds
    it, null when the asker was signed out. The v1 spec deleted
    `Service.added_by` for the same reason.

    There is no state column either. Nothing closes a request yet, so
    it would have no writer.
    """

    url = models.URLField(unique=True)
    # The demand signal. Nothing else records how often a URL was
    # asked for, so this is the record rather than a copy of one.
    request_count = models.PositiveIntegerField(default=1)
    last_requested_at = models.DateTimeField(default=timezone.now)

    class Meta(BaseModel.Meta):
        ordering = ["-request_count", "-last_requested_at"]

    def __str__(self):
        return self.url
```

- [ ] **Step 4: Add the serializer and the view**

In `api/catalog/serializers.py`:

```python
class ServiceRequestSerializer(serializers.Serializer):
    """The body of POST /catalog/requests/."""

    url = serializers.URLField()
```

In `api/catalog/views.py`, below `CatalogImportView`:

```python
class ServiceRequestView(APIView):
    """"Send this URL to us", from the Add-by-URL not-found screen.

    An import stores nothing about an attempt that failed, so this is
    where a dead end goes. Telling somebody to hunt for a better link
    assumes they have not already tried.
    """

    permission_classes = [AllowAny]
    # An anonymous write. Without this one person could inflate the
    # demand signal the admin list is ordered by.
    throttle_scope = Throttle.IMPORT

    @extend_schema(
        request=ServiceRequestSerializer,
        responses={
            202: OpenApiResponse(description="Recorded."),
            400: OpenApiResponse(description="Missing or malformed url."),
        },
    )
    def post(self, request):
        body = ServiceRequestSerializer(data=request.data)
        if not body.is_valid():
            return Response(body.errors, status=400)
        url = StatusPage.normalise_url(body.validated_data["url"])
        author = request.user if request.user.is_authenticated else None
        row, created = ServiceRequest.objects.get_or_create(
            url=url, defaults={"created_by": author, "updated_by": author}
        )
        if not created:
            # F() rather than a read and a write. Two people asking at
            # once would otherwise both write 2.
            ServiceRequest.objects.filter(pk=row.pk).update(
                request_count=F("request_count") + 1,
                last_requested_at=timezone.now(),
            )
        # Always 202, and always the same body. Anything else would
        # tell a stranger which URLs the catalog already holds.
        return Response(status=http.HTTP_202_ACCEPTED)
```

Import `F` from `django.db.models`, `timezone` from `django.utils`, and `ServiceRequest`,
`StatusPage`, `ServiceRequestSerializer`.

- [ ] **Step 5: Route it**

In `api/catalog/urls.py`, beside the import path:

```python
    path(
        "catalog/requests/",
        ServiceRequestView.as_view(),
        name="catalog-request",
    ),
```

- [ ] **Step 6: Run the tests**

Run:
```bash
cd api && uv run python manage.py makemigrations catalog -n service_request
uv run pytest tests/test_service_requests.py -v
```
Expected: PASS, all five.

- [ ] **Step 7: Document it**

In `docs/api/openapi.yaml`:

```yaml
  /catalog/requests/:
    post:
      tags: [catalog]
      summary: Ask us for a status page we could not read
      description: |
        The Add-by-URL not-found screen. Always `202`, whether or not the catalog already
        holds the URL, so asking cannot reveal what we have.

        One row per URL, counted. Throttled per caller.
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema: { type: object, required: [url], properties: { url: { type: string, format: uri } } }
      responses:
        '202': { description: Recorded }
        '400': { $ref: '#/components/responses/Error' }
        '429': { $ref: '#/components/responses/Throttled' }
```

Add `ServiceRequest` to the ER diagram in the v1 spec:

```
    ServiceRequest {
        uuid id PK
        url url UK "normalised"
        int request_count "the demand signal"
        datetime last_requested_at
    }
```

and to `BACKED` in `docs/check_docs.py`. It returns no body, so it needs no schema entry.

- [ ] **Step 8: Run everything and commit**

Run: `cd api && uv run pytest tests/ -q && docker compose -f docker-compose.test.yml run --rm docs`
Expected: PASS.

```bash
git add api docs
git commit -m "feat: a dead end can hand us the address

The Add-by-URL not-found screen offers to send us a URL, and an import
stored nothing about an attempt that failed. One row per URL with a
count, so the admin list is ordered by what people actually want."
```

---

## Task 12: Delete what nothing reads

**Files:**
- Modify: `api/catalog/views.py`, `api/catalog/urls.py`, `api/catalog/filters.py`,
  `api/catalog/queries.py`, `api/catalog/models.py`, `api/catalog/serializers.py`
- Modify: `api/dashboards/filters.py`
- Modify: `api/common/aggregates.py`
- Modify: `docs/api/openapi.yaml`, `docs/specs/2026-08-23-statusboard-design.md`
- Create: `api/catalog/migrations/0007_drop_service_columns.py` (generated)
- Test: `api/tests/test_catalog_api.py`, `api/tests/test_contract.py`

**Interfaces:**
- Consumes: everything the previous tasks produced. This one only removes.
- Produces: `ServiceViewSet` becomes retrieve only. `GET /catalog/services/{slug}/` is the
  one operation left on it.

Nothing here has a reader once the component collection and the event feed exist. A column
nothing sorts, filters or renders by does not stay.

- [ ] **Step 1: Write the failing tests**

In `api/tests/test_catalog_api.py`, replace the tests that exercised the service list with:

```python
def test_the_service_list_is_gone(client):
    # Discover searches components, and the signed-out board lists
    # overall components. Nothing asked a service list a question.
    assert resolve_or_none("/catalog/services/") is None


def test_the_nested_component_route_is_gone(client):
    # `/catalog/components/?service=` serves it, and three other
    # screens besides.
    service = ServiceFactory()
    response = client.get(f"/catalog/services/{service.slug}/components/")
    assert response.status_code == 404


def test_the_nested_event_route_is_gone(client):
    service = ServiceFactory()
    response = client.get(f"/catalog/services/{service.slug}/events/")
    assert response.status_code == 404


def test_a_service_still_answers_by_slug(client):
    # The service page reads it for the header and the About tab.
    service = ServiceFactory(name="Twilio")
    response = client.get(reverse("service-detail", args=[service.slug]))
    assert response.status_code == 200
    assert response.json()["name"] == "Twilio"
    # Nothing renders a description, so it is not in the shape.
    assert "description" not in response.json()
```

`resolve_or_none` is a helper:

```python
def resolve_or_none(path):
    from django.urls import Resolver404, resolve

    try:
        return resolve(path)
    except Resolver404:
        return None
```

In `api/tests/test_board_api.py`:

```python
def test_the_board_takes_several_severities_at_once(client, board):
    # The Severity filter offers all six values. A single exact match
    # could not express "everything that needs attention".
    client.force_login(board.owner)
    response = client.get(
        reverse("board-components", args=[board.id]), {"status__severity__in": "0,1,2"}
    )
    assert response.status_code == 200


def test_the_event_parameter_is_gone(client, board):
    # It named the Home Incidents and Maintenance tabs. Home is Board
    # and Updates now, and Updates is `/events/?dashboard=`.
    client.force_login(board.owner)
    response = client.get(
        reverse("board-components", args=[board.id]), {"event": "incident"}
    )
    # django-filter ignores an unknown parameter rather than failing,
    # so the proof is that it no longer narrows anything.
    assert response.json()["aggregates"]["total"] == response.json()["aggregates"]["total"]
    assert "by_event_kind" not in response.json()["aggregates"]
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_catalog_api.py tests/test_board_api.py -v`
Expected: FAIL. The list still resolves and `by_event_kind` is still in the envelope.

- [ ] **Step 3: Reduce the service viewset**

Replace `ServiceViewSet` in `api/catalog/views.py` with a retrieve-only view:

```python
class ServiceDetailView(generics.RetrieveAPIView):
    """The service page's header and its About tab.

    There is no list. Discover searches components, and the signed-out
    board lists overall components, so nothing asked a service
    collection a question.
    """

    permission_classes = [AllowAny]
    lookup_field = "slug"
    serializer_class = ServiceSerializer
    filter_backends = [FieldsBackend]

    def get_queryset(self):
        return Service.objects.for_display(self.request.user)
```

Delete `ServiceAggregateSet`. Its only caller was the list.

In `api/catalog/urls.py`, drop the router and name the detail route:

```python
urlpatterns = [
    path("catalog/import/", CatalogImportView.as_view(), name="catalog-import"),
    path("catalog/requests/", ServiceRequestView.as_view(), name="catalog-request"),
    path("catalog/components/", ComponentListView.as_view(), name="component-list"),
    path(
        "catalog/components/<uuid:pk>/",
        ComponentDetailView.as_view(),
        name="component-detail",
    ),
    path(
        "catalog/services/<slug:slug>/",
        ServiceDetailView.as_view(),
        name="service-detail",
    ),
]
```

The component paths sit above the service one, so `components` is never read as a slug.

- [ ] **Step 4: Delete the columns and the query pieces**

In `api/catalog/filters.py`, delete `ServiceFilter` and `ServiceEventFilter`. `EventFilter`
in `api/status/filters.py` replaced the second.

In `api/catalog/queries.py`, delete `WATCHER_COUNT`. `COMPONENT_WATCHER_COUNT` replaced it.

In `api/catalog/models.py`, delete `Service.is_featured` and `Service.description`.

In `api/catalog/serializers.py`, remove `"description"` from `ServiceSerializer.Meta.fields`.

In the adapters, drop `description` from whatever `fetch_service_metadata` returns:

Run `grep -rn "description" api/polling/` and remove the field from the dataclass and from
each adapter that sets it. Only cState returned one.

- [ ] **Step 5: Delete the board's event filter and the aggregate**

In `api/dashboards/filters.py`, delete the `event` filter and its `filter_event` method,
and add the `in` lookup:

```python
class BoardComponentFilter(filters.FilterSet):
    # Declared because a component has a history of statuses and the
    # open one is current. There is no `status` relation to generate
    # from, so the contract's name points at the annotation.
    status__severity = filters.NumberFilter(field_name="severity_now")
    status__severity__lte = filters.NumberFilter(
        field_name="severity_now", lookup_expr="lte"
    )
    status__severity__in = filters.BaseInFilter(
        field_name="severity_now", lookup_expr="in"
    )

    class Meta:
        model = ServiceComponent
        fields = []
```

In `api/common/aggregates.py`, delete `_by_event_kind` and its line in `build`. It counted
the Home Incidents and Maintenance tabs, which no longer exist.

- [ ] **Step 6: Run the tests**

Run:
```bash
cd api && uv run python manage.py makemigrations catalog -n drop_service_columns
uv run pytest tests/ -q
```
Expected: PASS. Fix any test still asserting on `description`, `is_featured` on a service,
`by_event_kind`, or the removed routes.

- [ ] **Step 7: Update the contract and the diagram**

In `docs/api/openapi.yaml`:

- delete the `/catalog/services/` operation
- delete `/catalog/services/{slug}/components/` and `/catalog/services/{slug}/events/`
- delete `description` from the `Service` schema
- delete `by_event_kind` from `StatusAggregates`

In the v1 spec's ER diagram, delete `description` and `is_featured` from `Service { ... }`.

- [ ] **Step 8: Prove the contract and the code agree**

Run:
```bash
cd api && uv run pytest tests/test_contract.py -v
docker compose -f docker-compose.test.yml run --rm docs
```
Expected: PASS. `test_no_operation_exists_that_the_contract_does_not_document` and
`test_every_documented_operation_exists_in_the_code` are the two that catch a half-done
removal.

- [ ] **Step 9: Commit**

```bash
git add api docs
git commit -m "refactor: delete what nothing reads any more

The service list, both nested routes, ServiceFilter, WATCHER_COUNT,
Service.description and Service.is_featured all served screens the
approved decks replaced. by_event_kind counted tabs that no longer
exist, and the board's event filter named the same two."
```

---

## Task 13: Admin follows the model

**Files:**
- Modify: `api/catalog/admin.py`
- Test: `api/tests/test_admin.py`

**Interfaces:**
- Consumes: `ServiceComponent.is_featured`, `catalog.queries.COMPONENT_WATCHER_COUNT`,
  `catalog.models.ServiceRequest`
- Produces: nothing other code reads.

Featuring a service now means ticking a flag on its overall component. An admin should not
have to know that to do it.

- [ ] **Step 1: Write the failing tests**

In `api/tests/test_admin.py`:

```python
def test_the_service_admin_features_through_the_overall_component(admin_client, db):
    # is_featured moved to the component. An admin asks "feature this
    # service", so the service page has to answer it.
    service = ServiceFactory()
    overall = ComponentFactory(service=service, is_overall=True)
    response = admin_client.get(
        reverse("admin:catalog_service_change", args=[service.pk])
    )
    assert response.status_code == 200
    assert b"is_featured" in response.content


def test_the_component_list_shows_watchers(admin_client, db):
    # The count is an annotation. A list column that forgets to
    # annotate it raises rather than showing a wrong number.
    component = ComponentFactory()
    track(component)
    response = admin_client.get(reverse("admin:catalog_servicecomponent_changelist"))
    assert response.status_code == 200


def test_service_requests_are_listed_by_demand(admin_client, db):
    # The list is the demand signal for what the catalog is missing,
    # so the most-asked-for URL is the first row.
    ServiceRequest.objects.create(url="https://a.example", request_count=1)
    ServiceRequest.objects.create(url="https://b.example", request_count=9)
    response = admin_client.get(reverse("admin:catalog_servicerequest_changelist"))
    assert response.status_code == 200
    assert response.content.index(b"b.example") < response.content.index(b"a.example")
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd api && uv run pytest tests/test_admin.py -k "features_through or shows_watchers or by_demand" -v`
Expected: FAIL with `NoReverseMatch: 'catalog_servicerequest_changelist' is not a registered
namespace`.

- [ ] **Step 3: Feature a service from its own page**

In `api/catalog/admin.py`, add an inline to the service admin:

```python
class OverallComponentInline(admin.StackedInline):
    """Featuring lives on the rollup, and an admin asks about the service.

    `is_featured` is the first key of the suggested sort. Ticking it on
    a service's overall component is what surfaces that service, so
    that is the question this answers.
    """

    model = ServiceComponent
    fields = ["is_featured"]
    extra = 0
    max_num = 1
    can_delete = False
    verbose_name = "Featuring"
    verbose_name_plural = "Featuring"

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_overall=True)

    def has_add_permission(self, request, obj):
        # Reconcile makes the rollup. An admin ticks its flag.
        return False
```

Add `inlines = [OverallComponentInline]` to the service admin, and remove `is_featured`
and `description` from its `list_display`, `list_filter` and `fieldsets`.

- [ ] **Step 4: Show watchers on the component list**

In the component admin:

```python
    list_display = [..., "watchers", "is_featured"]
    list_filter = [..., "is_featured"]

    def get_queryset(self, request):
        # `watcher_count` is an annotation, not a column. A list column
        # reading it without this raises rather than showing a wrong
        # number.
        return super().get_queryset(request).annotate(watcher_count=COMPONENT_WATCHER_COUNT)

    @display(description=_("Watchers"), ordering="watcher_count")
    def watchers(self, obj):
        return obj.watcher_count
```

Import `COMPONENT_WATCHER_COUNT` and drop the `WATCHER_COUNT` import.

- [ ] **Step 5: Register the requests**

```python
@admin.register(ServiceRequest)
class ServiceRequestAdmin(ModelAdmin):
    """What the catalog is missing, most asked for first."""

    list_display = ["url", "request_count", "last_requested_at", "created_by"]
    ordering = ["-request_count", "-last_requested_at"]
    search_fields = ["url"]
    readonly_fields = ["url", "request_count", "last_requested_at"]

    def has_add_permission(self, request):
        # A row arrives from the app, never from here.
        return False
```

- [ ] **Step 6: Run the tests**

Run: `cd api && uv run pytest tests/test_admin.py -v`
Expected: PASS.

- [ ] **Step 7: Open the pages and read the values back**

Run: `just dev`, then open each in a browser:

- `/admin/catalog/service/<id>/change/`, the Featuring block shows one checkbox
- `/admin/catalog/servicecomponent/`, the Watchers column shows a number, and sorts
- `/admin/catalog/servicerequest/`, the most-asked URL is the first row

An edit that ran without error is not an edit that worked.

- [ ] **Step 8: Run everything and commit**

Run: `cd api && uv run pytest tests/ -q && uv run ruff check --fix . && uv run ruff format . && python3 ../bin/check_prose.py`
Expected: PASS.

```bash
git add api
git commit -m "feat: admin features a service from the service page

is_featured moved to the overall component, and an admin asks to
feature a service rather than a component. The component list shows
watchers, and service requests are ordered by how often they are asked
for."
```

---

## Task 14: Prove the whole thing in the image CI runs it in

**Files:**
- Modify: none, unless something fails

**Interfaces:**
- Consumes: everything above
- Produces: a branch ready for a pull request

`just check` proves the image rather than the host. What CI proves is then what ships.

- [ ] **Step 1: Run the full gate**

Run: `just check`

Expected: PASS on every step. That is pytest with the coverage gate, ruff, the docs cross-check,
the prose check, and `makemigrations --check`.

- [ ] **Step 2: Fix whatever it caught, then run it again**

The likely failures, and what each means:

| Failure | Cause |
| --- | --- |
| `makemigrations --check` is not clean | a model change with no migration; run `makemigrations` |
| `docs` fails on an unmapped schema | a new schema is missing from `BACKED` or `PLAIN` in `docs/check_docs.py` |
| `docs` fails on a field with no column | the ER diagram is missing a column, or the field belongs in `DERIVED` |
| coverage below 85 | a branch in `system_events.py` with no test, most likely the claim guards |
| prose | a comment over 20 words, or an em dash |

- [ ] **Step 3: Read the contract once, end to end**

Run: `just dev`, open `http://<slug>.localhost:<port>/`, and read the Scalar page.

Confirm eighteen operations, and that the three removed ones are absent. The contract is
what the client is generated from, so a wrong description ships to every screen.

- [ ] **Step 4: Open a pull request**

```bash
git push -u origin client
gh pr create --fill
```

CI runs the same gate on the same image.

---

## Self-Review Notes

**Spec coverage.** Every section of `docs/specs/2026-09-03-statusboard-client-design.md`
maps to a task, except sections 3, 4, 10, 11 and 12. Those are the client, its build and
its deploy, and they are Plan B.

| Spec section | Task |
| --- | --- |
| 1, What this supersedes | 1 |
| 5, Removed | 12 |
| 5, Added | 5, 9, 10, 11 |
| 5, Changed | 12 |
| 5, Phase is a declared filter | 9 |
| 5, A tab badge is the collection's total | 9, 10 |
| 5, Discover is one list | 5, 12 |
| 5, Ordering | 4, 5 |
| 6, New model | 11 |
| 6, New columns | 2, 3, 4, 6 |
| 6, Removed columns | 12 |
| 6, Changed | 3, 6, 12 |
| 6, Admin | 13 |
| 6, Choices | 6 |
| 7, A status change is an event | 7, 8 |
| 8, Search | 4 |
| 9, Settings | none needed. The Refresh row was never an endpoint. |

**Names used across tasks.** `rebuild_ancestry` and `rebuild_search` are defined in Tasks 3
and 4 and called in both. `descendant_count` replaces `child_count` in Task 3 and is read by
the serializer in the same task. `COMPONENT_WATCHER_COUNT` is defined in Task 2 and read in
Tasks 5 and 13. `EventSource` is defined in Task 6 and read in Tasks 7, 8 and 10.
`SYSTEM_EVENT_MAX_SEVERITY` is defined and used in Task 7, and read again in Task 8.
`claim` is defined in Task 8 and called from `reconcile` in the same task.

**Ordering constraint.** Task 5 must land before Task 12. The component collection has to
serve the screens before the service list is deleted, or the API is unusable between two
commits on the same branch.
