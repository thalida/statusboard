import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from polling.reconcile import rebuild_ancestry, rebuild_search
from status.choices import EventKind, IncidentPhase, Severity, StatusSource
from status.models import ComponentStatus, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory, track

pytestmark = pytest.mark.django_db


def _reading(component, severity):
    """The open status row, which is what `severity_now` reads."""
    return ComponentStatus.objects.create(
        component=component,
        severity=severity,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )


@pytest.fixture
def tree():
    service = ServiceFactory(name="Twilio")
    rollup = ComponentFactory(
        service=service, name="Twilio", is_overall=True, status_page_order=0
    )
    parent = ComponentFactory(
        service=service, name="Programmable Messaging", status_page_order=2
    )
    leaf = ComponentFactory(
        service=service, name="SMS", parent=parent, status_page_order=1
    )
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
    # exact match cannot serve it. Undeclared, django-filter drops the
    # parameter without a word and the operational row comes back too.
    _, rollup, parent, leaf = tree
    _reading(rollup, Severity.MAJOR_OUTAGE)
    _reading(parent, Severity.DEGRADED)
    _reading(leaf, Severity.OPERATIONAL)
    response = client.get(reverse("component-list"), {"status__severity__in": "0,1,2"})
    assert {r["name"] for r in response.json()["results"]} == {
        "Twilio",
        "Programmable Messaging",
    }


def test_the_detail_answers_by_uuid(client, tree):
    _, _, _, leaf = tree
    response = client.get(reverse("component-detail", args=[leaf.id]))
    assert response.status_code == 200
    assert response.json()["name"] == "SMS"


def test_the_collection_leaves_out_an_archived_component(client, tree):
    # A provider dropped it, so nothing lists it. The service badge
    # counts the same rows, and the two cannot count differently.
    _, _, _, leaf = tree
    # `update_fields`, because the fixture rebuilt this row's ancestry
    # and its search document after the factory made it.
    leaf.is_archived = True
    leaf.save(update_fields=["is_archived"])

    body = client.get(reverse("component-list")).json()
    assert body["aggregates"]["total"] == 2
    assert "SMS" not in [r["name"] for r in body["results"]]


def test_the_detail_refuses_an_archived_component(client, tree):
    # Archived components are not served anywhere. A row the list hides
    # and the detail answers would be two rules, not one.
    _, _, _, leaf = tree
    leaf.is_archived = True
    leaf.save(update_fields=["is_archived"])

    assert client.get(reverse("component-detail", args=[leaf.id])).status_code == 404


def test_a_query_keeps_the_rank_the_search_worked_out(client, tree):
    # The rollup carries the word in its own name. The other two match
    # only through their service. A default sort applied after the
    # search discards the rank, and then the list reads alphabetically.
    response = client.get(reverse("component-list"), {"q": "twilio"})
    assert response.json()["results"][0]["name"] == "Twilio"


def test_a_services_parts_keep_the_status_pages_own_order(client, tree):
    # The service tab shows the components in the order the provider
    # lists them. The suggested sort would put them in name order.
    service, _, _, _ = tree
    response = client.get(
        reverse("component-list"), {"service": service.slug, "is_overall": "false"}
    )
    assert [r["name"] for r in response.json()["results"]] == [
        "SMS",
        "Programmable Messaging",
    ]


def test_is_tracked_narrows_to_what_the_viewer_watches(tree):
    # Showing All, Tracked or Untracked. The flag is per viewer, so the
    # filter has to read the annotation and not a column.
    _, _, _, leaf = tree
    item = track(leaf)
    viewer = APIClient()
    viewer.force_authenticate(item.dashboard.owner)
    response = viewer.get(reverse("component-list"), {"is_tracked": "true"})
    assert [r["name"] for r in response.json()["results"]] == ["SMS"]


def test_signed_out_nothing_is_tracked(client, tree):
    # Nobody signed out tracks anything, so Tracked is empty for them.
    response = client.get(reverse("component-list"), {"is_tracked": "true"})
    assert response.json()["results"] == []


def test_signed_out_everything_is_untracked(client, tree):
    # The same fact makes Untracked the whole list. Comparing against
    # the annotation instead reads `NOT NULL`, which SQL answers NULL,
    # and Untracked renders empty for a signed-out reader.
    response = client.get(reverse("component-list"), {"is_tracked": "false"})
    assert {r["name"] for r in response.json()["results"]} == {
        "Twilio",
        "Programmable Messaging",
        "SMS",
    }


def test_event_narrows_to_the_components_one_event_affects(client, tree):
    # An event's affected list. Only the components the provider names
    # on that event belong on it.
    service, _, parent, _ = tree
    event = ServiceEvent.objects.create(
        service=service,
        external_id="inc-1",
        kind=EventKind.INCIDENT,
        title="Messages are delayed",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    event.affected_components.add(parent)
    response = client.get(reverse("component-list"), {"event": str(event.id)})
    assert [r["name"] for r in response.json()["results"]] == ["Programmable Messaging"]


def test_a_ranked_search_pages_without_repeating_a_row(client):
    """`?q=` is Discover's default path, and `rank` ties heavily.

    Identical documents rank identically. A page boundary inside a run
    of ties is where a cursor repeats a row or skips one. Infinite
    scroll then shows the fault.
    """
    service = ServiceFactory(name="Twilio")
    for _ in range(7):
        ComponentFactory(service=service, name="SMS")
    rebuild_ancestry(service)
    rebuild_search(service)

    seen, pages = [], 0
    url = reverse("component-list")
    params = {"q": "twilio sms", "page_size": 2}
    while url:
        pages += 1
        # Seven rows, two a page. A cursor that repeats a page would
        # otherwise hang the suite rather than fail it.
        assert pages <= 4, "paging did not reach the end"
        body = client.get(url, params).json()
        seen += [row["id"] for row in body["results"]]
        url, params = body["next"], {}

    assert seen == list(dict.fromkeys(seen)), "a row came back on two pages"
    assert len(seen) == 7, "a row was never reached"


def test_the_path_leaves_out_an_archived_ancestor(client):
    # Each node carries an id a client links to, and the detail answers
    # 404 for an archived component. A breadcrumb step pointing at one
    # is a link to a page nothing serves.
    service = ServiceFactory()
    top = ComponentFactory(service=service, name="Messaging")
    middle = ComponentFactory(service=service, name="Programmable", parent=top)
    leaf = ComponentFactory(service=service, name="SMS", parent=middle)
    middle.is_archived = True
    middle.save(update_fields=["is_archived"])

    body = client.get(reverse("component-detail", args=[leaf.id])).json()

    assert [node["name"] for node in body["path"]] == ["Messaging"]
    # Shorter, not broken. `parent` is the raw column and still names
    # the archived row, so the two disagree by design.
    assert body["parent"] == str(middle.id)
