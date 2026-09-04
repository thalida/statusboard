import pytest
from django.urls import reverse
from django.utils import timezone

from authentication.models import User
from status.choices import EventKind, EventSource, IncidentPhase, MaintenancePhase
from status.models import EventUpdate, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory, track

pytestmark = pytest.mark.django_db


def _event(service, component, **kwargs):
    fields = {
        "kind": EventKind.INCIDENT,
        "title": "Something broke",
        "phase": IncidentPhase.INVESTIGATING,
        "starts_at": timezone.now(),
    }
    fields.update(kwargs)
    event = ServiceEvent.objects.create(service=service, **fields)
    event.affected_components.set([component])
    return event


def test_the_feed_lists_events_newest_first(client):
    # A feed is read from the top. Oldest first would open on an
    # incident from last month.
    service = ServiceFactory()
    component = ComponentFactory(service=service)
    _event(service, component, external_id="1", title="Older")
    new = _event(service, component, external_id="2", title="Newer")
    ServiceEvent.objects.filter(pk=new.pk).update(
        starts_at=timezone.now() + timezone.timedelta(minutes=5)
    )

    results = client.get(reverse("event-list")).json()["results"]
    assert [r["title"] for r in results] == ["Newer", "Older"]


def test_a_feed_row_names_its_service(client):
    # /events/?dashboard= spans every service on a board. A row cannot
    # label itself without the service it belongs to.
    service = ServiceFactory(slug="pagerduty")
    _event(service, ComponentFactory(service=service), external_id="1")

    results = client.get(reverse("event-list")).json()["results"]
    assert results[0]["service"]["slug"] == "pagerduty"


def test_service_narrows_the_feed(client):
    # A service's Updates tab. Anything from another service on it
    # would be answering a question nobody asked on that page.
    first = ServiceFactory()
    second = ServiceFactory()
    _event(first, ComponentFactory(service=first), external_id="1", title="Mine")
    _event(second, ComponentFactory(service=second), external_id="2", title="Theirs")

    results = client.get(reverse("event-list"), {"service": first.slug}).json()[
        "results"
    ]
    assert [r["title"] for r in results] == ["Mine"]


def test_component_narrows_the_feed(client):
    # A component's Updates tab reads the same collection one level
    # down, so it cannot be a different endpoint.
    service = ServiceFactory()
    wanted = ComponentFactory(service=service)
    other = ComponentFactory(service=service)
    _event(service, wanted, external_id="1", title="Wanted")
    _event(service, other, external_id="2", title="Other")

    results = client.get(reverse("event-list"), {"component": str(wanted.id)}).json()[
        "results"
    ]
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


def test_dashboard_narrows_to_what_you_track(authenticated_client, board):
    # Home's Updates tab. Everything posted across the services on
    # your board, and nothing else.
    #
    # `DEFAULT_AUTHENTICATION_CLASSES` is JWT only, so a plain
    # `force_login` leaves this view answering 401.
    # `authenticated_client` bears board.owner's own access token.
    tracked = ComponentFactory()
    untracked = ComponentFactory()
    track(tracked, user=board.owner)
    _event(tracked.service, tracked, external_id="1", title="Yours")
    _event(untracked.service, untracked, external_id="2", title="Not yours")

    results = authenticated_client.get(
        reverse("event-list"), {"dashboard": str(board.id)}
    ).json()["results"]
    assert [r["title"] for r in results] == ["Yours"]


def test_an_anonymous_caller_cannot_narrow_to_a_dashboard(client, board):
    # `get_object_or_404(..., owner=request.user)` would compare against
    # `AnonymousUser` and raise `TypeError` instead of answering cleanly.
    response = client.get(reverse("event-list"), {"dashboard": str(board.id)})
    assert response.status_code == 401


def test_a_dashboard_that_is_not_yours_is_not_readable(authenticated_client):
    # 404, not 403: a 403 would let anyone holding a valid token
    # confirm whether a board id exists.
    other = User.objects.create(email="someone-else@example.test")
    response = authenticated_client.get(
        reverse("event-list"), {"dashboard": str(other.default_dashboard.id)}
    )
    assert response.status_code == 404


def test_a_malformed_dashboard_id_is_a_400_not_a_500(authenticated_client):
    # `EventFilter`'s `dashboard` field is a `UUIDFilter`. A bad value
    # reaches django-filter and comes back like any other malformed
    # filter value. It must not surface as an unhandled ValueError.
    response = authenticated_client.get(
        reverse("event-list"), {"dashboard": "not-a-uuid"}
    )
    assert response.status_code == 400


def test_the_dashboard_filter_does_not_repeat_an_event(authenticated_client, board):
    # One event naming two components tracked on the same board is one
    # outage. Without .distinct() the M2M join returns one row per
    # matching component, and the feed shows it twice.
    service = ServiceFactory()
    first = ComponentFactory(service=service)
    second = ComponentFactory(service=service)
    track(first, user=board.owner)
    track(second, user=board.owner)
    event = _event(service, first, external_id="1", title="Shared")
    event.affected_components.add(second)

    results = authenticated_client.get(
        reverse("event-list"), {"dashboard": str(board.id)}
    ).json()["results"]
    assert [r["title"] for r in results] == ["Shared"]


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
    EventUpdate.objects.create(
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
