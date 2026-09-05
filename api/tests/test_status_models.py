import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils import timezone

from status.choices import (
    CLOSED_PHASES,
    EventKind,
    EventSource,
    IncidentPhase,
    MaintenancePhase,
    Severity,
    StatusSource,
)
from status.models import ComponentStatus, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory


@pytest.mark.django_db
def test_a_component_has_at_most_one_open_status():
    # The open row is the current one. Two open rows make every read ambiguous.
    component = ComponentFactory()
    ComponentStatus.objects.create(
        component=component,
        severity=Severity.OPERATIONAL,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )
    with pytest.raises(IntegrityError):
        ComponentStatus.objects.create(
            component=component,
            severity=Severity.MAJOR_OUTAGE,
            source=StatusSource.PROVIDER,
            started_at=timezone.now(),
        )


@pytest.mark.django_db
def test_closing_a_status_frees_the_slot_for_the_next_one():
    component = ComponentFactory()
    first = ComponentStatus.objects.create(
        component=component,
        severity=Severity.OPERATIONAL,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )
    first.ended_at = timezone.now()
    first.save(update_fields=["ended_at"])
    ComponentStatus.objects.create(
        component=component,
        severity=Severity.MAJOR_OUTAGE,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )
    assert ComponentStatus.objects.filter(component=component).count() == 2
    assert (
        ComponentStatus.objects.filter(
            component=component, ended_at__isnull=True
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_a_phase_must_belong_to_its_kind():
    # The pair cannot drift into a combination no provider would publish.
    event = ServiceEvent(
        service=ServiceFactory(),
        external_id="1",
        kind=EventKind.INCIDENT,
        title="x",
        phase=MaintenancePhase.SCHEDULED,
        starts_at=timezone.now(),
    )
    with pytest.raises(ValidationError):
        event.full_clean()


@pytest.mark.django_db
def test_a_matching_phase_validates():
    event = ServiceEvent(
        service=ServiceFactory(),
        external_id="1",
        kind=EventKind.INCIDENT,
        title="x",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    event.full_clean()


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
    fields = {
        "service": service,
        "kind": EventKind.INCIDENT,
        "title": "Outage",
        "phase": IncidentPhase.INVESTIGATING,
        "starts_at": timezone.now(),
    }
    ServiceEvent.objects.create(external_id="abc", **fields)
    with pytest.raises(IntegrityError):
        ServiceEvent.objects.create(external_id="abc", **fields)


def test_detected_is_an_open_phase(db):
    # A detected event is running. Listing it as closed would hide
    # every outage no provider ever wrote up.
    assert IncidentPhase.DETECTED not in CLOSED_PHASES
