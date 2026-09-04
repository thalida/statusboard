import pytest
from django.utils import timezone

from catalog.models import ServiceComponent
from polling.adapters.base import (
    NormalisedComponent,
    NormalisedEvent,
    NormalisedUpdate,
)
from polling.reconcile import apply_fetch, rebuild_ancestry, rebuild_search
from status.choices import (
    EventKind,
    EventSource,
    IncidentPhase,
    Severity,
    StatusSource,
)
from status.models import ComponentStatus, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory


def _component(external_id="a", name="SMS", severity=Severity.OPERATIONAL, **kw):
    return NormalisedComponent(
        external_id=external_id,
        name=name,
        severity=severity,
        parent_external_id=kw.get("parent"),
        order=kw.get("order", 0),
        is_overall=kw.get("is_overall", False),
    )


@pytest.mark.django_db
def test_a_new_component_is_created():
    service = ServiceFactory()
    apply_fetch(service, [_component()], [], StatusSource.PROVIDER)
    assert (
        ServiceComponent.objects.filter(service=service, external_id="a").count() == 1
    )


@pytest.mark.django_db
def test_a_rename_updates_the_existing_row_rather_than_creating_one():
    service = ServiceFactory()
    ComponentFactory(service=service, external_id="a", name="SMS")
    apply_fetch(
        service, [_component(name="Programmable Messaging")], [], StatusSource.PROVIDER
    )
    rows = ServiceComponent.objects.filter(service=service)
    assert rows.count() == 1
    assert rows.get().name == "Programmable Messaging"


@pytest.mark.django_db
def test_a_vanished_component_is_archived_not_deleted():
    # Someone may be tracking it. Deleting would silently remove it from their board.
    service = ServiceFactory()
    ComponentFactory(service=service, external_id="gone", name="Old")
    apply_fetch(service, [_component()], [], StatusSource.PROVIDER)
    old = ServiceComponent.objects.get(service=service, external_id="gone")
    assert old.archived_at is not None
    assert ServiceComponent.objects.filter(service=service).count() == 2


@pytest.mark.django_db
def test_a_component_that_reappears_is_unarchived():
    service = ServiceFactory()
    ComponentFactory(service=service, external_id="a", archived_at=timezone.now())
    apply_fetch(service, [_component()], [], StatusSource.PROVIDER)
    assert (
        ServiceComponent.objects.get(service=service, external_id="a").archived_at
        is None
    )


@pytest.mark.django_db
def test_the_parent_child_structure_is_refreshed():
    service = ServiceFactory()
    apply_fetch(
        service,
        [_component("parent", "Group"), _component("child", "SMS", parent="parent")],
        [],
        StatusSource.PROVIDER,
    )
    child = ServiceComponent.objects.get(service=service, external_id="child")
    assert child.parent.external_id == "parent"


@pytest.mark.django_db
def test_an_unchanged_severity_does_not_open_a_second_status_row():
    service = ServiceFactory()
    apply_fetch(service, [_component()], [], StatusSource.PROVIDER)
    apply_fetch(service, [_component()], [], StatusSource.PROVIDER)
    component = ServiceComponent.objects.get(service=service, external_id="a")
    assert ComponentStatus.objects.filter(component=component).count() == 1


@pytest.mark.django_db
def test_a_changed_severity_closes_the_old_row_and_opens_a_new_one():
    service = ServiceFactory()
    apply_fetch(service, [_component()], [], StatusSource.PROVIDER)
    apply_fetch(
        service, [_component(severity=Severity.MAJOR_OUTAGE)], [], StatusSource.PROVIDER
    )
    component = ServiceComponent.objects.get(service=service, external_id="a")
    rows = ComponentStatus.objects.filter(component=component).order_by("started_at")
    assert rows.count() == 2
    assert rows.first().ended_at is not None
    assert rows.last().ended_at is None
    assert rows.last().severity == Severity.MAJOR_OUTAGE


@pytest.mark.django_db
def test_an_event_is_upserted_on_its_provider_id():
    service = ServiceFactory()
    event = NormalisedEvent(
        external_id="inc-1",
        kind=EventKind.INCIDENT,
        title="First",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    apply_fetch(service, [], [event], StatusSource.PROVIDER)
    apply_fetch(
        service,
        [],
        [
            NormalisedEvent(
                **{
                    **event.__dict__,
                    "title": "Renamed",
                    "phase": IncidentPhase.RESOLVED,
                }
            )
        ],
        StatusSource.PROVIDER,
    )
    rows = ServiceEvent.objects.filter(service=service)
    assert rows.count() == 1
    assert rows.get().title == "Renamed"
    assert rows.get().phase == IncidentPhase.RESOLVED


@pytest.mark.django_db
def test_an_event_is_linked_to_the_components_it_names():
    service = ServiceFactory()
    apply_fetch(
        service,
        [_component("a"), _component("b")],
        [
            NormalisedEvent(
                external_id="inc-1",
                kind=EventKind.INCIDENT,
                title="x",
                phase=IncidentPhase.INVESTIGATING,
                starts_at=timezone.now(),
                affected_external_ids=("a",),
            )
        ],
        StatusSource.PROVIDER,
    )
    event = ServiceEvent.objects.get(service=service)
    assert [c.external_id for c in event.affected_components.all()] == ["a"]


@pytest.mark.django_db
def test_a_later_provider_post_joins_the_event_the_poll_opened():
    # A poll saw the drop before the provider wrote it up. Without the
    # claim the feed shows two cards for one outage.
    service = ServiceFactory()
    apply_fetch(
        service,
        [_component("a", severity=Severity.DEGRADED)],
        [],
        StatusSource.PROVIDER,
    )
    ours = ServiceEvent.objects.get(service=service)
    assert ours.detected_by == EventSource.SYSTEM

    apply_fetch(
        service,
        [_component("a", severity=Severity.DEGRADED)],
        [
            NormalisedEvent(
                external_id="inc-1",
                kind=EventKind.INCIDENT,
                title="Elevated SMS delivery failures",
                phase=IncidentPhase.INVESTIGATING,
                starts_at=timezone.now(),
                affected_external_ids=("a",),
                updates=(
                    NormalisedUpdate(
                        phase=IncidentPhase.INVESTIGATING,
                        body="We are looking into it",
                        posted_at=timezone.now(),
                    ),
                ),
            )
        ],
        StatusSource.PROVIDER,
    )

    event = ServiceEvent.objects.get(service=service)
    assert event.pk == ours.pk
    assert event.external_id == "inc-1"
    # We found it first, and a claim never rewrites that.
    assert event.detected_by == EventSource.SYSTEM
    assert event.updates.count() == 2


@pytest.mark.django_db
def test_a_run_stamps_what_it_wrote():
    # A wrong or stale reading is otherwise untraceable: you can see what
    # it says and not where it came from.
    from polling.models import PollRun
    from tests.factories import PollerFactory, StatusPageFactory

    service = ServiceFactory()
    page = StatusPageFactory(service=service)
    run = PollRun.objects.create(
        poller=PollerFactory(service=service),
        url=page.url,
        provider=page.provider,
        started_at=timezone.now(),
    )
    event = NormalisedEvent(
        external_id="inc-1",
        kind=EventKind.INCIDENT,
        title="x",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    apply_fetch(service, [_component()], [event], StatusSource.PROVIDER, run)

    assert ComponentStatus.objects.get(component__service=service).poll_run == run
    assert ServiceEvent.objects.get(service=service).poll_run == run


@pytest.mark.django_db
def test_a_hand_seeded_row_has_no_run():
    # apply_fetch is called without one when nothing polled.
    service = ServiceFactory()
    apply_fetch(service, [_component()], [], StatusSource.PROVIDER)
    assert ComponentStatus.objects.get(component__service=service).poll_run is None


@pytest.mark.django_db
def test_a_poll_signs_everything_it_writes():
    """Nobody types any of this, so nothing is left without an author.

    A blank author reads the same as one that was lost. A component
    carries no poll run either, so without this its origin was recorded
    nowhere at all.
    """
    from django.contrib.auth import get_user_model

    from status.models import EventUpdate

    service = ServiceFactory()
    event = NormalisedEvent(
        external_id="inc-1",
        kind=EventKind.INCIDENT,
        title="First",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
        updates=[
            NormalisedUpdate(
                phase=IncidentPhase.INVESTIGATING,
                body="Looking into it.",
                posted_at=timezone.now(),
            )
        ],
    )
    apply_fetch(service, [_component()], [event], StatusSource.PROVIDER)

    system = get_user_model().objects.system()
    for model in (ServiceComponent, ComponentStatus, ServiceEvent, EventUpdate):
        rows = model.objects.all()
        assert rows.exists(), model.__name__
        assert not rows.filter(created_by__isnull=True).exists(), model.__name__
        assert rows.exclude(created_by=system).count() == 0, model.__name__


@pytest.mark.django_db
def test_a_second_poll_does_not_rewrite_who_made_the_row():
    # A row records who made it once. Re-signing it on every poll would
    # make `created_at` and `created_by` disagree.
    service = ServiceFactory()
    apply_fetch(service, [_component()], [], StatusSource.PROVIDER)
    first = ServiceComponent.objects.get()

    apply_fetch(service, [_component(name="Renamed")], [], StatusSource.PROVIDER)

    again = ServiceComponent.objects.get()
    assert again.created_by_id == first.created_by_id
    assert again.created_at == first.created_at


@pytest.mark.django_db
def test_a_poll_writes_the_ancestor_chain():
    # Nothing else writes the column. Without this pass a component's
    # Components tab lists no descendant, whatever the provider nests.
    service = ServiceFactory()
    apply_fetch(
        service,
        [_component(external_id="a"), _component(external_id="b", parent="a")],
        [],
        StatusSource.PROVIDER,
    )

    top = ServiceComponent.objects.get(external_id="a")
    child = ServiceComponent.objects.get(external_id="b")
    assert top.ancestor_ids == []
    assert child.ancestor_ids == [top.id]


@pytest.mark.django_db
def test_a_poll_rebuilds_the_service_once_not_once_a_component(monkeypatch):
    # `ServiceComponent.save` rebuilds the whole service, and this pass
    # saves every component of it. Unsuppressed, a hundred components
    # cost a hundred rebuilds of a hundred rows, on every poll.
    from polling import reconcile

    calls = []
    real = reconcile.rebuild_ancestry
    monkeypatch.setattr(
        reconcile,
        "rebuild_ancestry",
        lambda service: calls.append(service) or real(service),
    )

    service = ServiceFactory()
    rows = [_component(external_id=str(n)) for n in range(5)]
    apply_fetch(service, rows, [], StatusSource.PROVIDER)
    assert len(calls) == 1

    calls.clear()
    apply_fetch(service, rows, [], StatusSource.PROVIDER)
    assert len(calls) == 1


@pytest.mark.django_db
def test_a_reparent_rewrites_the_subtree():
    # The chain of a grandchild changes when its parent moves, and
    # nothing tells the grandchild. The pass rewrites the service.
    service = ServiceFactory()
    nested = [
        _component(external_id="a"),
        _component(external_id="b", parent="a"),
        _component(external_id="c", parent="b"),
    ]
    apply_fetch(service, nested, [], StatusSource.PROVIDER)

    moved = [
        _component(external_id="a"),
        _component(external_id="b"),
        _component(external_id="c", parent="b"),
    ]
    apply_fetch(service, moved, [], StatusSource.PROVIDER)

    assert ServiceComponent.objects.get(external_id="c").ancestor_ids == [
        ServiceComponent.objects.get(external_id="b").id
    ]


@pytest.mark.django_db
def test_a_loop_in_the_parent_column_does_not_hang_the_pass():
    # The column points at its own table, so bad data can make a cycle.
    # Without the guard the walk never reaches a root, and the worker
    # never finishes the poll that called it.
    service = ServiceFactory()
    first = ComponentFactory(service=service)
    second = ComponentFactory(service=service, parent=first)
    # `update` skips `clean`, which is the only thing refusing this.
    ServiceComponent.objects.filter(pk=first.pk).update(parent=second)

    rebuild_ancestry(service)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.ancestor_ids == [second.id]
    assert second.ancestor_ids == [first.id]


@pytest.mark.django_db
def test_a_reparent_rewrites_every_descendants_path():
    # Ancestry and the search vector both carry the chain. A provider
    # moving one node must not leave its children searchable under
    # where they used to sit.
    service = ServiceFactory(name="Acme")
    old = ComponentFactory(service=service, name="Legacy", external_id="old")
    new = ComponentFactory(service=service, name="Platform", external_id="new")
    leaf = ComponentFactory(
        service=service, name="Queue", external_id="leaf", parent=old
    )
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
