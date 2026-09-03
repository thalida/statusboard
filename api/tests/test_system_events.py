import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from polling.system_events import reconcile_system_events
from status.choices import (
    EventKind,
    EventSource,
    IncidentPhase,
    MaintenancePhase,
    Severity,
    StatusSource,
)
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
    return get_user_model().objects.system()


def test_an_unexplained_outage_opens_an_event():
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


def test_an_explained_outage_opens_nothing():
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


def test_a_service_wide_incident_explains_its_service():
    # One outage is one card. A provider incident naming no component
    # covers every component of that service.
    service = ServiceFactory()
    _status(ComponentFactory(service=service), Severity.DEGRADED)
    ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.INCIDENT,
        title="Everything is down",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )

    reconcile_system_events(service, _author())

    assert ServiceEvent.objects.filter(detected_by=EventSource.SYSTEM).count() == 0


def test_a_service_wide_maintenance_window_explains_nothing():
    # A planned window is not an account of an outage. Read as one, a
    # provider doing scheduled work hides every outage beside it.
    service = ServiceFactory()
    _status(ComponentFactory(service=service), Severity.DEGRADED)
    ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.MAINTENANCE,
        title="Planned work",
        phase=MaintenancePhase.IN_PROGRESS,
        starts_at=timezone.now(),
    )

    reconcile_system_events(service, _author())

    assert ServiceEvent.objects.filter(detected_by=EventSource.SYSTEM).count() == 1


def test_unknown_opens_nothing():
    # Severity 3 is our own poll failing to read their page. Calling
    # that their incident would report our fault as theirs.
    service = ServiceFactory()
    _status(ComponentFactory(service=service), Severity.UNKNOWN)

    reconcile_system_events(service, _author())

    assert ServiceEvent.objects.count() == 0


def test_every_transition_while_open_writes_an_update():
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


def test_a_poll_that_changes_nothing_posts_nothing():
    # Without this every poll beat posts a duplicate update to an open
    # card. The timeline then reads one line per beat, not per change.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.DEGRADED)

    reconcile_system_events(service, _author())
    reconcile_system_events(service, _author())

    event = ServiceEvent.objects.get(service=service)
    assert event.updates.count() == 1


def test_unknown_holds_the_event_open():
    # Unknown is our poll failing to read their page. Closing on it
    # tells somebody an outage ended when we stopped being able to see.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.MAJOR_OUTAGE)
    reconcile_system_events(service, _author())

    ComponentStatus.objects.filter(component=component, ended_at__isnull=True).update(
        ended_at=timezone.now()
    )
    _status(component, Severity.UNKNOWN)
    reconcile_system_events(service, _author())

    event = ServiceEvent.objects.get(service=service)
    assert event.phase == IncidentPhase.DETECTED
    assert event.ends_at is None


def test_recovery_closes_the_event():
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
