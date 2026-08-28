"""Nothing of one service may point at another service's rows.

Every one of these was allowed before. A foreign key names a row, never
whose row it is, so the database cannot refuse any of them: the service
is one join away and Postgres has no way to compare across that without
a trigger. So the rules live on the models, the pickers in the admin
offer only what is allowed, and these hold both in place.
"""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from catalog.models import ServiceComponent
from polling.adapters.base import NormalisedComponent, NormalisedEvent
from polling.models import PollRun
from polling.reconcile import apply_fetch
from status.choices import EventKind, IncidentPhase, Severity, StatusSource
from status.models import ComponentStatus, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory


@pytest.fixture
def two_services():
    return ServiceFactory(name="One"), ServiceFactory(name="Two")


def _run(service):
    return PollRun.objects.create(
        poller=service.poller,
        url="https://status.example.com/",
        provider="statuspage",
        started_at=timezone.now(),
        finished_at=timezone.now(),
        ok=True,
    )


@pytest.mark.django_db
def test_a_component_cannot_sit_under_another_services_component(two_services):
    mine, theirs = two_services
    child = ComponentFactory(service=mine)
    child.parent = ComponentFactory(service=theirs)

    with pytest.raises(ValidationError) as raised:
        child.full_clean()
    assert "parent" in raised.value.message_dict


@pytest.mark.django_db
def test_a_component_cannot_be_its_own_parent(two_services):
    mine, _ = two_services
    component = ComponentFactory(service=mine)
    component.parent = component

    with pytest.raises(ValidationError):
        component.full_clean()


@pytest.mark.django_db
def test_a_component_may_sit_under_its_own_services_component(two_services):
    mine, _ = two_services
    child = ComponentFactory(service=mine, external_id="child")
    child.parent = ComponentFactory(service=mine, external_id="parent")

    child.full_clean()


@pytest.mark.django_db
def test_a_reading_cannot_cite_a_poll_of_another_service(two_services):
    mine, theirs = two_services
    reading = ComponentStatus(
        component=ComponentFactory(service=mine),
        severity=Severity.OPERATIONAL,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
        poll_run=_run(theirs),
    )

    with pytest.raises(ValidationError) as raised:
        reading.full_clean()
    assert "poll_run" in raised.value.message_dict


@pytest.mark.django_db
def test_an_event_cannot_cite_a_poll_of_another_service(two_services):
    mine, theirs = two_services
    event = ServiceEvent(
        service=mine,
        external_id="inc-1",
        kind=EventKind.INCIDENT,
        title="Something",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
        poll_run=_run(theirs),
    )

    with pytest.raises(ValidationError) as raised:
        event.full_clean()
    assert "poll_run" in raised.value.message_dict


@pytest.mark.django_db
def test_an_event_names_components_of_another_service(two_services):
    """The relation is set after the save, so `clean` cannot see it.

    The admin drops the strays and says so. This is what it asks.
    """
    mine, theirs = two_services
    event = ServiceEvent.objects.create(
        service=mine,
        external_id="inc-1",
        kind=EventKind.INCIDENT,
        title="Something",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    event.affected_components.add(ComponentFactory(service=mine))
    stray = ComponentFactory(service=theirs)
    event.affected_components.add(stray)

    assert list(event.components_of_another_service()) == [stray]


@pytest.mark.django_db
def test_a_poll_cannot_write_to_the_service_it_did_not_read(two_services):
    mine, theirs = two_services

    with pytest.raises(ValueError, match="A poll writes to the service it read"):
        apply_fetch(mine, [], [], StatusSource.PROVIDER, _run(theirs))


@pytest.mark.django_db
def test_a_poll_writes_to_the_service_it_read(two_services):
    mine, _ = two_services

    apply_fetch(mine, [], [], StatusSource.PROVIDER, _run(mine))


@pytest.mark.django_db
def test_an_event_keeps_a_component_the_provider_stopped_listing(two_services):
    """`rows` holds only what this fetch described.

    Read from that alone, an event lost its link to any component that
    dropped off the page, and the incident then affected nothing.
    """
    mine, _ = two_services
    ComponentFactory(service=mine, external_id="sms", name="SMS")

    apply_fetch(
        mine,
        [NormalisedComponent("voice", "Voice", Severity.OPERATIONAL, None, 0, False)],
        [
            NormalisedEvent(
                external_id="inc-1",
                kind=EventKind.INCIDENT,
                title="SMS is down",
                phase=IncidentPhase.INVESTIGATING,
                starts_at=timezone.now(),
                affected_external_ids=["sms"],
            )
        ],
        StatusSource.PROVIDER,
    )

    event = ServiceEvent.objects.get(external_id="inc-1")
    assert [c.name for c in event.affected_components.all()] == ["SMS"]


@pytest.mark.django_db
def test_a_poll_invents_no_component(two_services):
    # An id matching nothing is dropped. A component the provider never
    # described would show on the catalog and on boards as if it had.
    mine, _ = two_services

    apply_fetch(
        mine,
        [],
        [
            NormalisedEvent(
                external_id="inc-1",
                kind=EventKind.INCIDENT,
                title="Something",
                phase=IncidentPhase.INVESTIGATING,
                starts_at=timezone.now(),
                affected_external_ids=["never-seen"],
            )
        ],
        StatusSource.PROVIDER,
    )

    assert not ServiceComponent.objects.filter(external_id="never-seen").exists()
    assert (
        ServiceEvent.objects.get(external_id="inc-1").affected_components.count() == 0
    )
