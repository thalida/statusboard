import pytest
from django.utils import timezone

from catalog.models import ServiceComponent
from polling.adapters.base import NormalisedComponent, NormalisedEvent
from polling.reconcile import apply_fetch
from status.choices import EventKind, IncidentPhase, Severity, StatusSource
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
