import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from dashboards.models import Dashboard, DashboardItem
from status.choices import (
    EventKind,
    IncidentPhase,
    MaintenancePhase,
    Severity,
    StatusSource,
)
from status.models import ComponentStatus, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory, StatusPageFactory


@pytest.fixture
def board(db):
    user = User.objects.create(email="a@b.com")
    return Dashboard.objects.get(owner=user, is_default=True)


@pytest.fixture
def client(board):
    from rest_framework_simplejwt.tokens import RefreshToken

    api = APIClient()
    api.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(board.owner).access_token}"
    )
    return api


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
def test_the_incidents_tab_filters_on_event_kind(client, board):
    with_incident = _track(board)
    _event(with_incident, EventKind.INCIDENT, IncidentPhase.INVESTIGATING)
    _track(board)
    url = reverse("board-components", kwargs={"uuid": board.id}) + "?event=incident"
    assert len(client.get(url).json()["results"]) == 1


@pytest.mark.django_db
def test_a_resolved_incident_does_not_put_a_row_on_the_incidents_tab(client, board):
    component = _track(board)
    _event(
        component, EventKind.INCIDENT, IncidentPhase.RESOLVED, ends_at=timezone.now()
    )
    url = reverse("board-components", kwargs={"uuid": board.id}) + "?event=incident"
    assert client.get(url).json()["results"] == []


@pytest.mark.django_db
def test_the_event_filter_binds_both_conditions_to_the_same_event(client, board):
    # `ServiceEvent` and `ServiceComponent` are many-to-many.
    # Two parameters filter twice and can match two different events.
    component = _track(board)
    _event(
        component, EventKind.INCIDENT, IncidentPhase.RESOLVED, ends_at=timezone.now()
    )
    _event(component, EventKind.MAINTENANCE, MaintenancePhase.IN_PROGRESS)
    url = reverse("board-components", kwargs={"uuid": board.id}) + "?event=incident"
    assert client.get(url).json()["results"] == []


@pytest.mark.django_db
def test_scheduled_maintenance_appears_on_the_maintenance_tab_while_reading_operational(
    client, board
):
    # A window three days out leaves severity 5.
    # Severity cannot select it, so the tab filters on the event.
    component = _track(board, severity=Severity.OPERATIONAL)
    _event(
        component,
        EventKind.MAINTENANCE,
        MaintenancePhase.SCHEDULED,
        starts_at=timezone.now() + timezone.timedelta(days=3),
    )
    url = reverse("board-components", kwargs={"uuid": board.id}) + "?event=maintenance"
    rows = client.get(url).json()["results"]
    assert len(rows) == 1
    assert rows[0]["status"]["severity"] == Severity.OPERATIONAL


@pytest.mark.django_db
def test_one_fetch_fills_every_chip(client, board):
    # One response must fill all three chips.
    # Otherwise the client makes a request per chip.
    broken = _track(board, severity=Severity.MAJOR_OUTAGE)
    _event(broken, EventKind.INCIDENT, IncidentPhase.INVESTIGATING)
    planned = _track(board)
    _event(planned, EventKind.MAINTENANCE, MaintenancePhase.SCHEDULED)
    aggregates = client.get(
        reverse("board-components", kwargs={"uuid": board.id})
    ).json()["aggregates"]
    assert aggregates["total"] == 2
    assert aggregates["by_event_kind"]["incident"] == 1
    assert aggregates["by_event_kind"]["maintenance"] == 1
    assert "next_refresh_at" in aggregates
    assert "oldest_refreshed_at" in aggregates


@pytest.mark.django_db
def test_severity_composes_with_a_tab(client, board):
    down = _track(board, severity=Severity.MAJOR_OUTAGE)
    _event(down, EventKind.INCIDENT, IncidentPhase.INVESTIGATING)
    up = _track(board, severity=Severity.OPERATIONAL)
    _event(up, EventKind.INCIDENT, IncidentPhase.MONITORING)
    url = (
        reverse("board-components", kwargs={"uuid": board.id})
        + "?event=incident&status__severity__lte=3"
    )
    assert len(client.get(url).json()["results"]) == 1


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
    component = ComponentFactory(service=ServiceFactory(watcher_count=0))
    url = reverse("board-components", kwargs={"uuid": board.id})
    response = client.post(url, {"component_id": str(component.id)}, format="json")
    assert response.status_code == 201
    assert DashboardItem.objects.filter(dashboard=board, component=component).exists()
    component.service.refresh_from_db()
    assert component.service.watcher_count == 1


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
    # Someone tracking five Twilio components is one watcher. Counting
    # items would let one person outrank a crowd in the suggestion order.
    service = ServiceFactory()
    StatusPageFactory(service=service)
    url = reverse("board-components", kwargs={"uuid": board.id})
    for external_id in ("a", "b", "c"):
        component = ComponentFactory(service=service, external_id=external_id)
        client.post(url, {"component_id": str(component.id)}, format="json")
    service.refresh_from_db()
    assert service.watcher_count == 1


@pytest.mark.django_db
def test_two_people_tracking_one_service_count_twice(client, board):
    service = ServiceFactory()
    StatusPageFactory(service=service)
    component = ComponentFactory(service=service)
    DashboardItem.objects.create(dashboard=board, component=component)

    other = Dashboard.objects.get(owner=User.objects.create(email="second@b.com"))
    DashboardItem.objects.create(dashboard=other, component=component)

    service.refresh_watcher_count()
    service.refresh_from_db()
    assert service.watcher_count == 2


@pytest.mark.django_db
def test_untracking_the_last_component_drops_the_watcher(client, board):
    component = _track(board)
    service = component.service
    service.refresh_watcher_count()
    client.delete(
        reverse(
            "board-component-detail",
            kwargs={"uuid": board.id, "component_id": component.id},
        )
    )
    service.refresh_from_db()
    assert service.watcher_count == 0
