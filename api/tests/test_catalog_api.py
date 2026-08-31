import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from status.choices import (
    EventKind,
    IncidentPhase,
    MaintenancePhase,
    Severity,
    StatusSource,
)
from status.models import ComponentStatus, ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory, StatusPageFactory


def _with_status(service, severity, is_overall=False, external_id=None):
    component = ComponentFactory(
        service=service,
        is_overall=is_overall,
        external_id=external_id or f"e{severity}",
    )
    ComponentStatus.objects.create(
        component=component,
        severity=severity,
        source=StatusSource.PROVIDER,
        started_at=timezone.now(),
    )
    return component


@pytest.mark.django_db
def test_the_list_is_public():
    assert APIClient().get(reverse("service-list")).status_code == 200


@pytest.mark.django_db
def test_every_list_response_uses_the_same_envelope():
    body = APIClient().get(reverse("service-list")).json()
    assert set(body) == {"aggregates", "next", "results"}
    assert "total" in body["aggregates"]


@pytest.mark.django_db
def test_a_service_nests_its_overall_component_rather_than_copying_its_fields():
    service = ServiceFactory(slug="twilio")
    StatusPageFactory(service=service)
    _with_status(service, Severity.MAJOR_OUTAGE, is_overall=True)
    body = APIClient().get(reverse("service-list")).json()["results"][0]
    assert body["overall_component"]["status"]["severity"] == Severity.MAJOR_OUTAGE
    assert "severity" not in body


@pytest.mark.django_db
def test_the_overall_component_is_a_plain_component():
    # One shape everywhere, so one renderer draws every row.
    service = ServiceFactory()
    StatusPageFactory(service=service)
    _with_status(service, Severity.OPERATIONAL, is_overall=True)
    overall = (
        APIClient()
        .get(reverse("service-list"))
        .json()["results"][0]["overall_component"]
    )
    for field in (
        "id",
        "name",
        "path",
        "parent",
        "child_count",
        "is_overall",
        "archived_at",
        "status",
        "upcoming_maintenance",
        "upcoming_maintenance_count",
        "active_incident",
        "active_incident_count",
        "service",
        "is_tracked",
    ):
        assert field in overall, f"{field} missing from the overall component"


@pytest.mark.django_db
def test_severity_filters_use_the_orm_path():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    _with_status(service, Severity.MAJOR_OUTAGE, is_overall=True)
    url = reverse("service-list") + "?overall_component__status__severity__lte=3"
    assert len(APIClient().get(url).json()["results"]) == 1
    url = reverse("service-list") + "?overall_component__status__severity__lte=0"
    assert len(APIClient().get(url).json()["results"]) == 1


@pytest.mark.django_db
def test_fields_prunes_the_response():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    _with_status(service, Severity.OPERATIONAL, is_overall=True)
    body = (
        APIClient()
        .get(reverse("service-list") + "?fields=id,name")
        .json()["results"][0]
    )
    assert set(body) == {"id", "name"}


@pytest.mark.django_db
def test_a_dotted_field_path_prunes_inside_a_nested_object():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    _with_status(service, Severity.OPERATIONAL, is_overall=True)
    url = reverse("service-list") + "?fields=id,overall_component.status.severity"
    body = APIClient().get(url).json()["results"][0]
    assert set(body) == {"id", "overall_component"}
    assert set(body["overall_component"]) == {"status"}
    assert set(body["overall_component"]["status"]) == {"severity"}


@pytest.mark.django_db
def test_active_incident_excludes_resolved_ones():
    # A resolved incident with a count of unresolved ones shows "+0 more".
    service = ServiceFactory()
    StatusPageFactory(service=service)
    component = _with_status(service, Severity.OPERATIONAL, is_overall=True)
    resolved = ServiceEvent.objects.create(
        service=service,
        external_id="1",
        kind=EventKind.INCIDENT,
        title="Old",
        phase=IncidentPhase.RESOLVED,
        starts_at=timezone.now(),
        ends_at=timezone.now(),
    )
    resolved.affected_components.add(component)
    overall = (
        APIClient()
        .get(reverse("service-list"))
        .json()["results"][0]["overall_component"]
    )
    assert overall["active_incident"] is None
    assert overall["active_incident_count"] == 0


@pytest.mark.django_db
def test_upcoming_maintenance_excludes_finished_windows():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    component = _with_status(service, Severity.OPERATIONAL, is_overall=True)
    past = ServiceEvent.objects.create(
        service=service,
        external_id="m1",
        kind=EventKind.MAINTENANCE,
        title="Old window",
        phase=MaintenancePhase.COMPLETED,
        starts_at=timezone.now() - timezone.timedelta(days=30),
        ends_at=timezone.now() - timezone.timedelta(days=29),
    )
    past.affected_components.add(component)
    overall = (
        APIClient()
        .get(reverse("service-list"))
        .json()["results"][0]["overall_component"]
    )
    assert overall["upcoming_maintenance"] is None
    assert overall["upcoming_maintenance_count"] == 0


@pytest.mark.django_db
def test_the_events_endpoint_returns_both_kinds_and_filters_on_kind():
    service = ServiceFactory(slug="twilio")
    StatusPageFactory(service=service)
    ServiceEvent.objects.create(
        service=service,
        external_id="1",
        kind=EventKind.INCIDENT,
        title="I",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    ServiceEvent.objects.create(
        service=service,
        external_id="2",
        kind=EventKind.MAINTENANCE,
        title="M",
        phase=MaintenancePhase.SCHEDULED,
        starts_at=timezone.now(),
    )
    url = reverse("service-events", kwargs={"slug": "twilio"})
    assert len(APIClient().get(url).json()["results"]) == 2
    assert len(APIClient().get(url + "?kind=incident").json()["results"]) == 1


@pytest.mark.django_db
def test_the_events_aggregate_is_by_phase_only():
    service = ServiceFactory(slug="twilio")
    StatusPageFactory(service=service)
    url = reverse("service-events", kwargs={"slug": "twilio"})
    aggregates = APIClient().get(url).json()["aggregates"]
    assert set(aggregates) == {"total", "by_phase"}


@pytest.mark.django_db
def test_an_event_carries_no_component_ids():
    # The projection runs one way: a component carries its event, not the reverse.
    service = ServiceFactory(slug="twilio")
    StatusPageFactory(service=service)
    ServiceEvent.objects.create(
        service=service,
        external_id="1",
        kind=EventKind.INCIDENT,
        title="I",
        phase=IncidentPhase.INVESTIGATING,
        starts_at=timezone.now(),
    )
    url = reverse("service-events", kwargs={"slug": "twilio"})
    row = APIClient().get(url).json()["results"][0]
    assert set(row) == {
        "id",
        "kind",
        "title",
        "phase",
        "starts_at",
        "ends_at",
        "updates",
    }


@pytest.mark.django_db
def test_suggestions_put_what_is_broken_ahead_of_what_is_popular():
    """Severity sits ahead of popularity on purpose.

    A middling service that is broken now beats a popular one that is
    fine. That is the premise of the public view.
    """
    popular = ServiceFactory(name="Popular", tracked=500)
    StatusPageFactory(service=popular)
    _with_status(popular, Severity.OPERATIONAL, is_overall=True)

    broken = ServiceFactory(name="Broken", tracked=1)
    StatusPageFactory(service=broken)
    _with_status(broken, Severity.MAJOR_OUTAGE, is_overall=True)

    names = [
        r["name"] for r in APIClient().get(reverse("service-list")).json()["results"]
    ]
    assert names.index("Broken") < names.index("Popular")


@pytest.mark.django_db
def test_a_featured_service_still_leads():
    # Featured is the cold-start seed. On day one nothing has watchers
    # and nothing is polled, so it is the whole list.
    plain = ServiceFactory(name="Plain")
    StatusPageFactory(service=plain)
    _with_status(plain, Severity.MAJOR_OUTAGE, is_overall=True)

    featured = ServiceFactory(name="Featured", is_featured=True)
    StatusPageFactory(service=featured)
    _with_status(featured, Severity.OPERATIONAL, is_overall=True)

    names = [
        r["name"] for r in APIClient().get(reverse("service-list")).json()["results"]
    ]
    assert names.index("Featured") < names.index("Plain")


@pytest.mark.django_db
def test_a_service_with_no_reading_sorts_last_not_first():
    # Never seen is not the same as healthy, and it must not pose as
    # broken either.
    unread = ServiceFactory(name="Unread")
    StatusPageFactory(service=unread)

    healthy = ServiceFactory(name="Healthy")
    StatusPageFactory(service=healthy)
    _with_status(healthy, Severity.OPERATIONAL, is_overall=True)

    names = [
        r["name"] for r in APIClient().get(reverse("service-list")).json()["results"]
    ]
    assert names.index("Healthy") < names.index("Unread")
