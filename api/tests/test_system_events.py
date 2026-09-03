from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from polling.system_events import claim, reconcile_system_events
from status.choices import (
    EventKind,
    EventSource,
    IncidentPhase,
    MaintenancePhase,
    Severity,
    StatusSource,
)
from status.models import ComponentStatus, EventUpdate, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory

pytestmark = pytest.mark.django_db


def _status(component, severity, started_at=None):
    ComponentStatus.objects.create(
        component=component,
        severity=severity,
        source=StatusSource.PROVIDER,
        started_at=started_at or timezone.now(),
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


def test_a_provider_event_claims_the_one_we_opened():
    # One outage is one card. Two cards for one outage is what the
    # claim exists to prevent.
    service = ServiceFactory()
    component = ComponentFactory(service=service, name="SMS")
    voice = ComponentFactory(service=service, name="Voice")
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
    provider.affected_components.set([component, voice])
    EventUpdate.objects.create(
        event=provider,
        phase=IncidentPhase.INVESTIGATING,
        body="We are looking into it",
        posted_at=provider.starts_at,
    )

    assert claim(provider, _author()) is True

    ours.refresh_from_db()
    assert ours.external_id == "abc"
    assert ours.title == "Elevated SMS delivery failures"
    assert ours.phase == IncidentPhase.INVESTIGATING
    # Ours records who found it, and a claim never rewrites that.
    assert ours.detected_by == EventSource.SYSTEM
    assert not ServiceEvent.objects.filter(pk=provider.pk).exists()
    # Their post moves before their row goes. Deleting first would
    # cascade the timeline away.
    assert ours.updates.count() == 2
    assert {u.source for u in ours.updates.all()} == {
        EventSource.SYSTEM,
        EventSource.PROVIDER,
    }
    # Their event named a component ours did not. Losing it would drop
    # that component from the card.
    assert set(ours.affected_components.all()) == {component, voice}


def test_a_stale_provider_event_claims_nothing():
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


def test_a_maintenance_window_claims_nothing():
    # A claim copies their phase onto ours. A maintenance phase on an
    # incident is a combination no provider publishes.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.DEGRADED)
    reconcile_system_events(service, _author())
    ours = ServiceEvent.objects.get(service=service)

    provider = ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.MAINTENANCE,
        title="Planned work",
        phase=MaintenancePhase.IN_PROGRESS,
        starts_at=ours.starts_at,
    )
    provider.affected_components.set([component])

    assert claim(provider, _author()) is False
    ours.refresh_from_db()
    assert ours.phase == IncidentPhase.DETECTED


def test_one_of_ours_claims_nothing():
    # A claim runs on a provider's row. Ours would match itself, take
    # its own id and delete the row it was folding into.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.DEGRADED)
    reconcile_system_events(service, _author())
    ours = ServiceEvent.objects.get(service=service)

    assert claim(ours, _author()) is False
    assert ServiceEvent.objects.count() == 1


def test_a_claimed_event_is_not_claimed_twice():
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


def test_archiving_a_component_closes_our_open_event():
    # We can no longer watch it recover, so the event could never
    # close. A red row would stay on a board for good.
    service = ServiceFactory()
    component = ComponentFactory(service=service, name="SMS")
    _status(component, Severity.MAJOR_OUTAGE)
    reconcile_system_events(service, _author())

    component.is_archived = True
    component.save(update_fields=["is_archived"])
    reconcile_system_events(service, _author())

    event = ServiceEvent.objects.get(service=service)
    component.refresh_from_db()
    assert event.phase == IncidentPhase.RESOLVED
    # The end is when the provider dropped it, not when we noticed.
    # Stamping now would report an outage that ran until this poll.
    assert event.ends_at == component.archived_at
    assert event.updates.latest("posted_at").body == "SMS is no longer published"


def test_an_archived_component_opens_nothing():
    # Opening one we can never watch recover writes a card that closes
    # in the same pass, once per poll.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _status(component, Severity.MAJOR_OUTAGE)
    component.is_archived = True
    component.save(update_fields=["is_archived"])

    reconcile_system_events(service, _author())

    assert ServiceEvent.objects.count() == 0


def test_the_nearest_start_wins_when_several_could_be_claimed():
    # Their post explains the outage that began beside it. The further
    # event is another outage, and their updates would land on it.
    service = ServiceFactory()
    early = ComponentFactory(service=service, name="SMS")
    late = ComponentFactory(service=service, name="Voice")
    now = timezone.now()
    _status(early, Severity.DEGRADED, started_at=now - timedelta(minutes=30))
    _status(late, Severity.DEGRADED, started_at=now - timedelta(minutes=5))
    reconcile_system_events(service, _author())
    further = ServiceEvent.objects.get(affected_components=early)
    nearer = ServiceEvent.objects.get(affected_components=late)

    provider = ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.INCIDENT,
        title="Elevated failures",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=now - timedelta(minutes=6),
    )
    provider.affected_components.set([early, late])

    assert claim(provider, _author()) is True

    nearer.refresh_from_db()
    further.refresh_from_db()
    assert nearer.external_id == "abc"
    assert further.external_id is None


def test_a_claimed_event_stays_open_while_one_component_is_bad():
    # A claim merges their components onto ours. One recovery is no
    # account of the others, and a closed card is minted again next poll.
    service = ServiceFactory()
    sms = ComponentFactory(service=service, name="SMS")
    voice = ComponentFactory(service=service, name="Voice")
    _status(sms, Severity.MAJOR_OUTAGE)
    _status(voice, Severity.OPERATIONAL)
    reconcile_system_events(service, _author())
    ours = ServiceEvent.objects.get(service=service)

    provider = ServiceEvent.objects.create(
        service=service,
        external_id="abc",
        kind=EventKind.INCIDENT,
        title="Elevated failures",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=ours.starts_at,
    )
    provider.affected_components.set([sms, voice])
    assert claim(provider, _author()) is True

    reconcile_system_events(service, _author())
    reconcile_system_events(service, _author())

    ours.refresh_from_db()
    assert ours.phase == IncidentPhase.INVESTIGATING
    assert ours.ends_at is None
    assert ServiceEvent.objects.count() == 1
