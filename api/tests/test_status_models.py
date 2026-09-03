import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils import timezone

from status.choices import (
    EventKind,
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


@pytest.mark.django_db
def test_an_event_may_name_no_component_at_all():
    # A provider publishes some events against the service.
    # A component FK cannot hold them.
    event = ServiceEvent.objects.create(
        service=ServiceFactory(),
        external_id="1",
        kind=EventKind.MAINTENANCE,
        title="x",
        phase=MaintenancePhase.SCHEDULED,
        starts_at=timezone.now(),
    )
    assert event.affected_components.count() == 0
