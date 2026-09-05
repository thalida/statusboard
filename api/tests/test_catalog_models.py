import pytest
from django.db.utils import IntegrityError

from catalog.models import Service, ServiceComponent, StatusPage
from tests.factories import (
    ComponentFactory,
    PollerFactory,
    ServiceFactory,
    UserFactory,
    ancestry,
    descendants,
    track,
    watchers,
)


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


@pytest.mark.django_db
def test_a_component_is_identified_by_external_id_not_by_name():
    # Names change. Provider ids do not.
    # A name match orphans a tracked row on the first rename.
    service = ServiceFactory()
    ComponentFactory(service=service, external_id="abc", name="SMS")
    with pytest.raises(IntegrityError):
        ComponentFactory(
            service=service, external_id="abc", name="Programmable Messaging"
        )


@pytest.mark.django_db
def test_the_same_external_id_may_exist_under_a_different_service():
    ComponentFactory(service=ServiceFactory(slug="a"), external_id="abc")
    ComponentFactory(service=ServiceFactory(slug="b"), external_id="abc")
    assert ServiceComponent.objects.filter(external_id="abc").count() == 2


@pytest.mark.django_db
def test_status_page_url_is_the_dedupe_key():
    StatusPage.objects.create(
        service=ServiceFactory(slug="a"), url="https://x/", provider="statuspage"
    )
    with pytest.raises(IntegrityError):
        StatusPage.objects.create(
            service=ServiceFactory(slug="b"), url="https://x/", provider="statuspage"
        )


@pytest.mark.django_db
def test_poller_intervals_are_null_to_inherit_the_deployment_default():
    # The Service signal makes it, so there is one to read already.
    poller = ServiceFactory().poller
    assert poller.interval_seconds is None
    assert poller.effective_interval_seconds == 300


@pytest.mark.django_db
def test_a_service_can_override_the_interval():
    poller = PollerFactory(service=ServiceFactory(), interval_seconds=60)
    assert poller.effective_interval_seconds == 60


@pytest.mark.django_db
def test_a_component_can_be_archived_rather_than_deleted():
    # Someone may track this component.
    # Deletion removes it from their board with no warning.
    component = ComponentFactory()
    component.is_archived = True
    component.save()
    component.refresh_from_db()
    assert component.is_archived
    assert component.archived_at is not None


@pytest.mark.django_db
def test_a_service_slugs_itself_from_its_name():
    # Nobody should have to type the URL of a service they are adding.
    assert Service.objects.create(name="Twilio SendGrid").slug == "twilio-sendgrid"


@pytest.mark.django_db
def test_a_second_service_with_the_same_name_gets_a_counter():
    # Two providers really can share a name, so this cannot just fail.
    Service.objects.create(name="Status")
    assert Service.objects.create(name="Status").slug == "status-2"
    assert Service.objects.create(name="Status").slug == "status-3"


@pytest.mark.django_db
def test_a_slug_given_by_hand_is_kept():
    assert Service.objects.create(name="Twilio", slug="twil").slug == "twil"


@pytest.mark.django_db
def test_renaming_a_service_does_not_move_its_slug():
    # The slug is the service's public URL. A rename must not break it.
    service = Service.objects.create(name="Twilio")
    service.name = "Twilio Messaging"
    service.save()
    assert service.slug == "twilio"


@pytest.mark.django_db
def test_a_name_with_no_slug_characters_still_gets_one():
    assert Service.objects.create(name="!!!").slug == "service"


@pytest.mark.django_db
def test_archiving_sets_the_date():
    # `updated_at` cannot answer when a provider dropped a component. It
    # moves on every save, so a later rename would erase it.
    component = ComponentFactory()
    assert component.archived_at is None

    component.is_archived = True
    component.save()

    assert component.archived_at is not None


@pytest.mark.django_db
def test_unarchiving_clears_the_date():
    component = ComponentFactory()
    component.is_archived = True
    component.save()

    component.is_archived = False
    component.save()

    assert component.archived_at is None


@pytest.mark.django_db
def test_the_flag_and_the_date_cannot_disagree():
    """One fact, two columns, so the database holds them together.

    A bulk update never reaches `save`, which is the path that would
    otherwise let them come apart quietly.
    """
    from django.db import IntegrityError, transaction

    from catalog.models import ServiceComponent

    component = ComponentFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        ServiceComponent.objects.filter(pk=component.pk).update(is_archived=True)


@pytest.mark.django_db
def test_the_database_refuses_a_component_parented_under_the_rollup():
    """A bulk write skips `clean`. Only the trigger is left to refuse it.

    `ComponentFactory` calls `objects.create`, never `full_clean`. A
    poll or a shell session meets this, never a form's `clean` error.
    """
    service = ServiceFactory()
    rollup = ComponentFactory(service=service, is_overall=True)
    with pytest.raises(IntegrityError):
        ComponentFactory(service=service, parent=rollup)


@pytest.mark.django_db
def test_the_database_refuses_a_rollup_that_already_has_children():
    """The same rule, met from the other side.

    A component can gain the rollup flag after it already has
    children, since `is_overall` is editable. The trigger checks both
    directions, or promoting an existing parent would corrupt every
    descendant count under it.
    """
    from django.db import IntegrityError, transaction

    service = ServiceFactory()
    parent = ComponentFactory(service=service)
    ComponentFactory(service=service, parent=parent)

    parent.is_overall = True
    with pytest.raises(IntegrityError), transaction.atomic():
        parent.save()


def test_a_parent_in_another_service_is_not_a_step_in_the_path(db):
    # The walk stops at the service boundary. A breadcrumb that went
    # past it names a component of another service. The same response
    # then says the row has no ancestors.
    old = ServiceFactory(name="Twilio")
    top = ComponentFactory(service=old, name="Programmable Messaging")
    leaf = ComponentFactory(service=old, name="SMS", parent=top)

    top.service = ServiceFactory(name="Vonage")
    top.save()

    leaf.refresh_from_db()
    assert leaf.ancestors == []
    assert leaf.visible_ancestors == []
    assert leaf.path == "Twilio / SMS"


def test_the_tree_reads_every_step_not_one_level(db):
    # A component's Components tab lists everything under it, and its
    # breadcrumb names every step above it. One level either way would
    # hide the grandchild and shorten the path.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    leaf = ComponentFactory(service=service, parent=middle)

    # Root first, which is the order a breadcrumb reads.
    assert ancestry(leaf) == [top.id, middle.id]
    assert descendants(top) == {middle.id, leaf.id}
    # Nothing counts a component among the rows below it.
    assert descendants(leaf) == set()


def test_the_tree_stops_at_the_service_boundary(db):
    # Moving a component to another service leaves its old children
    # pointing across. Counting them under the mover names rows that
    # service's lists never hold.
    old = ServiceFactory()
    top = ComponentFactory(service=old)
    leaf = ComponentFactory(service=old, parent=top)

    top.service = ServiceFactory()
    top.save()

    assert descendants(top) == set()
    leaf.refresh_from_db()
    assert ancestry(leaf) == []


def test_a_loop_in_the_parent_column_does_not_hang_the_tree(db):
    # The column points at its own table, so bad data can make a cycle.
    # Unguarded, the walk down never ends and the request never answers.
    service = ServiceFactory()
    first = ComponentFactory(service=service)
    second = ComponentFactory(service=service, parent=first)
    # `update` skips `clean`, which is the only thing refusing this.
    ServiceComponent.objects.filter(pk=first.pk).update(parent=second)

    assert descendants(first) == {second.id}
    first.refresh_from_db()
    second.refresh_from_db()
    assert ancestry(first) == [second.id]
    assert ancestry(second) == [first.id]


def test_deleting_a_component_takes_its_ancestry_with_it(db):
    # An array of ids held no reference, and a closure table needed a
    # rebuild hook on four write paths. A computed answer passes this
    # trivially, which is why the table went.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    leaf = ComponentFactory(service=service, parent=middle)

    middle.delete()

    # `parent` is SET_NULL, so the leaf is now a root. Nothing may
    # still claim it sits under the grandparent.
    leaf.refresh_from_db()
    assert ancestry(leaf) == []
    assert descendants(top) == set()


def test_for_display_counts_descendants_without_a_query_a_row(
    db, django_assert_num_queries
):
    # The count is why `for_display` exists. Asked per row, a page of
    # fifty components costs fifty extra queries.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    ComponentFactory(service=service, parent=middle)

    rows = list(ServiceComponent.objects.for_display())
    with django_assert_num_queries(0):
        counts = sorted(row.descendant_count for row in rows)

    # Two below the top, one below the middle, none below the leaf.
    assert counts == [0, 1, 2]


def test_the_descendant_count_leaves_out_an_archived_row(db):
    # The badge and the list below it read one number. If this counted
    # an archived row, the tab would say 2 and then show one component.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    leaf = ComponentFactory(service=service, parent=middle)
    leaf.is_archived = True
    leaf.save(update_fields=["is_archived"])

    row = ServiceComponent.objects.for_display().get(pk=top.pk)
    assert row.descendant_count == 1


def test_the_descendant_count_walks_through_an_archived_row(db):
    # An archived group is not counted, and it does not hide what sits
    # under it either. A walk that stopped there would drop live rows
    # the Components tab still lists.
    service = ServiceFactory()
    top = ComponentFactory(service=service)
    middle = ComponentFactory(service=service, parent=top)
    ComponentFactory(service=service, parent=middle)
    middle.is_archived = True
    middle.save(update_fields=["is_archived"])

    row = ServiceComponent.objects.for_display().get(pk=top.pk)
    assert row.descendant_count == 1


def test_a_component_read_without_for_display_has_no_count(db):
    # The count is an annotation and nothing falls back to a query. A
    # serving path that forgets `for_display` has to fail loudly, not
    # ask once a row.
    top = ComponentFactory()
    ComponentFactory(service=top.service, parent=top)

    row = ServiceComponent.objects.get(pk=top.pk)
    with pytest.raises(AttributeError):
        assert row.descendant_count


def test_a_services_component_count_leaves_out_an_archived_row(db):
    # This is the badge on the service page. The Components tab under it
    # lists the same rows, and the two cannot count differently.
    service = ServiceFactory()
    ComponentFactory(service=service)
    gone = ComponentFactory(service=service)
    gone.is_archived = True
    gone.save()

    assert Service.objects.for_display().get(pk=service.pk).component_count == 1


def test_a_services_tracked_count_leaves_out_an_archived_row(db):
    # The client reads a count above zero as "this service is on your
    # board". The board list leaves an archived row out. A count that
    # held one promised a row the board never returns.
    user = UserFactory()
    service = ServiceFactory()
    gone = ComponentFactory(service=service)
    track(gone, user=user)
    gone.is_archived = True
    gone.save()

    prepared = Service.objects.for_display(user).get(pk=service.pk)
    assert prepared.tracked_component_count == 0


def test_a_services_tracked_count_counts_a_component_once_per_owner(db):
    # A person may own several boards. The count says how many of this
    # service's components are on them. Counting the join rows makes one
    # component held twice read as two, above a tab listing one.
    from dashboards.models import Dashboard, DashboardItem

    user = UserFactory()
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    track(component, user=user)
    second = Dashboard.objects.create(owner=user)
    DashboardItem.objects.create(dashboard=second, component=component)

    prepared = Service.objects.for_display(user).get(pk=service.pk)
    assert prepared.tracked_component_count == 1


def test_search_reaches_a_component_through_its_services_name(db):
    # "twilio" has to find SMS. Its own name says nothing about which
    # service publishes it. A name-only match returns an empty page for
    # the word people actually type.
    service = ServiceFactory(name="Twilio")
    rollup = ComponentFactory(service=service, name="Twilio", is_overall=True)
    parent = ComponentFactory(service=service, name="Programmable Messaging")
    leaf = ComponentFactory(service=service, name="SMS", parent=parent)

    assert set(ServiceComponent.objects.search("twilio")) == {rollup, parent, leaf}

    # OR semantics would let the rollup match too: it says "twilio" but
    # never "sms".
    assert list(ServiceComponent.objects.search("twilio sms")) == [leaf]


def test_search_ignores_the_case_and_matches_part_of_a_word(db):
    # People type a fragment in lower case. An exact match would answer
    # nothing until the whole name was typed the provider's way.
    service = ServiceFactory(name="Twilio")
    leaf = ComponentFactory(service=service, name="Programmable Messaging")

    assert list(ServiceComponent.objects.search("messag")) == [leaf]
