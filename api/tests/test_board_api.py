import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from dashboards.models import Dashboard, DashboardItem
from status.choices import (
    EventKind,
    IncidentPhase,
    Severity,
    StatusSource,
)
from status.models import ComponentStatus, ServiceEvent
from tests.factories import (
    ComponentFactory,
    ServiceFactory,
    StatusPageFactory,
    watchers,
)


@pytest.fixture
def client(authenticated_client):
    # Every test in this module reads or writes one board as its
    # owner. The plain `client` fixture stays anonymous everywhere
    # else, so this override is local to this module.
    return authenticated_client


def _track(board, severity=Severity.OPERATIONAL, slug=None):
    service = ServiceFactory(slug=slug) if slug else ServiceFactory()
    StatusPageFactory(service=service)
    component = ComponentFactory(service=service, is_overall=True)
    ComponentStatus.objects.create(
        component=component,
        severity=severity,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )
    DashboardItem.objects.create(dashboard=board, component=component)
    return component


def _event(component, kind, phase, starts_at=None, ends_at=None):
    event = ServiceEvent.objects.create(
        service=component.service,
        external_id=f"{kind}-{component.id}",
        kind=kind,
        title="x",
        phase=phase,
        starts_at=starts_at or timezone.now(),
        ends_at=ends_at,
    )
    event.affected_components.add(component)
    return event


@pytest.mark.django_db
def test_the_board_requires_authentication(board):
    url = reverse("board-components", kwargs={"uuid": board.id})
    assert APIClient().get(url).status_code == 401


@pytest.mark.django_db
def test_all_returns_every_tracked_component(client, board):
    _track(board)
    _track(board)
    url = reverse("board-components", kwargs={"uuid": board.id})
    assert client.get(url).json()["aggregates"]["total"] == 2


@pytest.mark.django_db
def test_one_fetch_fills_every_chip(client, board):
    # One response must fill every chip on the board.
    # Otherwise the client makes a request per chip.
    _track(board, severity=Severity.MAJOR_OUTAGE)
    _track(board, severity=Severity.OPERATIONAL)
    aggregates = client.get(
        reverse("board-components", kwargs={"uuid": board.id})
    ).json()["aggregates"]
    assert aggregates["total"] == 2
    assert aggregates["by_severity"][str(Severity.MAJOR_OUTAGE)] == 1
    assert aggregates["by_severity"][str(Severity.OPERATIONAL)] == 1
    assert "next_refresh_at" in aggregates
    assert "oldest_refreshed_at" in aggregates


@pytest.mark.django_db
def test_the_board_takes_several_severities_at_once(client, board):
    # The Severity filter offers all six values. A single exact match
    # could not express "everything that needs attention".
    _track(board, severity=Severity.MAJOR_OUTAGE)
    _track(board, severity=Severity.PARTIAL_OUTAGE)
    _track(board, severity=Severity.OPERATIONAL)
    response = client.get(
        reverse("board-components", kwargs={"uuid": board.id}),
        {"status__severity__in": "0,1,2"},
    )
    assert response.status_code == 200
    severities = {r["status"]["severity"] for r in response.json()["results"]}
    assert severities == {Severity.MAJOR_OUTAGE, Severity.PARTIAL_OUTAGE}


@pytest.mark.django_db
def test_the_event_parameter_is_gone(client, board):
    # It named the Home Incidents and Maintenance tabs. Home is Board
    # and Updates now, and Updates is `/events/?dashboard=`.
    with_incident = _track(board)
    _event(with_incident, EventKind.INCIDENT, IncidentPhase.INVESTIGATING)
    _track(board)
    body = client.get(
        reverse("board-components", kwargs={"uuid": board.id}), {"event": "incident"}
    ).json()
    # django-filter ignores an unknown parameter rather than failing,
    # so the proof is that it no longer narrows anything.
    assert body["aggregates"]["total"] == 2
    assert "by_event_kind" not in body["aggregates"]


@pytest.mark.django_db
def test_all_sorts_worst_first_by_default(client, board):
    _track(board, severity=Severity.OPERATIONAL)
    _track(board, severity=Severity.MAJOR_OUTAGE)
    rows = client.get(reverse("board-components", kwargs={"uuid": board.id})).json()[
        "results"
    ]
    assert rows[0]["status"]["severity"] == Severity.MAJOR_OUTAGE


@pytest.mark.django_db
def test_tracking_a_component_adds_it_and_bumps_the_watcher_count(client, board):
    component = ComponentFactory(service=ServiceFactory())
    url = reverse("board-components", kwargs={"uuid": board.id})
    response = client.post(url, {"component_id": str(component.id)}, format="json")
    assert response.status_code == 201
    assert DashboardItem.objects.filter(dashboard=board, component=component).exists()
    assert watchers(component) == 1


@pytest.mark.django_db
def test_tracking_the_same_component_twice_is_not_an_error(client, board):
    component = ComponentFactory()
    url = reverse("board-components", kwargs={"uuid": board.id})
    client.post(url, {"component_id": str(component.id)}, format="json")
    second = client.post(url, {"component_id": str(component.id)}, format="json")
    assert second.status_code in (200, 201)
    assert DashboardItem.objects.filter(dashboard=board).count() == 1


@pytest.mark.django_db
def test_stopping_tracking_removes_the_item(client, board):
    component = _track(board)
    url = reverse(
        "board-component-detail",
        kwargs={"uuid": board.id, "component_id": component.id},
    )
    assert client.delete(url).status_code == 204
    assert DashboardItem.objects.filter(dashboard=board).count() == 0


@pytest.mark.django_db
def test_a_board_belonging_to_someone_else_is_not_readable(client):
    other = Dashboard.objects.get(owner=User.objects.create(email="c@d.com"))
    url = reverse("board-components", kwargs={"uuid": other.id})
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_watcher_count_is_distinct_users_not_tracked_items(client, board):
    # One person tracking a component from two boards is one watcher.
    # Counting items would let one person outrank a crowd in the
    # suggestion order.
    component = ComponentFactory()
    second_board = Dashboard.objects.create(owner=board.owner, name="Second")
    for target in (board, second_board):
        url = reverse("board-components", kwargs={"uuid": target.id})
        client.post(url, {"component_id": str(component.id)}, format="json")
    assert watchers(component) == 1


@pytest.mark.django_db
def test_two_people_tracking_one_component_count_twice(client, board):
    service = ServiceFactory()
    StatusPageFactory(service=service)
    component = ComponentFactory(service=service)
    DashboardItem.objects.create(dashboard=board, component=component)

    other = Dashboard.objects.get(owner=User.objects.create(email="second@b.com"))
    DashboardItem.objects.create(dashboard=other, component=component)

    assert watchers(component) == 2


@pytest.mark.django_db
def test_untracking_the_last_component_drops_the_watcher(client, board):
    component = _track(board)
    assert watchers(component) == 1
    client.delete(
        reverse(
            "board-component-detail",
            kwargs={"uuid": board.id, "component_id": component.id},
        )
    )
    assert watchers(component) == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "how",
    ["the admin", "closing the account", "deleting the board", "a bulk delete"],
)
def test_the_watcher_count_is_right_however_a_row_arrives_or_goes(how):
    """It decides what gets polled, so the door must not matter.

    It used to be a column, kept true by overriding save and delete.
    Three of these cascade in SQL and reached neither. A service kept a
    watcher who was gone, and the poller kept polling it.
    """
    from django.contrib.auth import get_user_model

    from dashboards.models import Dashboard, DashboardItem

    service = ServiceFactory()
    component = ComponentFactory(service=service)
    user = get_user_model().objects.create(email="watcher@b.com")
    board = Dashboard.objects.create(owner=user, name="B")
    DashboardItem.objects.create(dashboard=board, component=component)
    assert watchers(component) == 1

    if how == "the admin":
        DashboardItem.objects.get(dashboard=board, component=component).delete()
    elif how == "closing the account":
        user.delete()
    elif how == "deleting the board":
        Dashboard.objects.create(owner=user, name="Other")
        board.delete()
    else:
        DashboardItem.objects.all().delete()

    assert watchers(component) == 0
