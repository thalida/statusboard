import pytest
from django.urls import Resolver404, resolve, reverse
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
from tests.factories import (
    ComponentFactory,
    ServiceFactory,
    StatusPageFactory,
    track,
)


def resolve_or_none(path):
    """The view a path reaches, or None when nothing serves it."""
    try:
        return resolve(path)
    except Resolver404:
        return None


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


def _service_detail(service):
    return APIClient().get(reverse("service-detail", args=[service.slug])).json()


def test_the_service_list_is_gone():
    # Discover searches components, and the signed-out board lists
    # overall components. Nothing asked a service list a question.
    assert resolve_or_none("/catalog/services/") is None


@pytest.mark.django_db
def test_the_nested_component_route_is_gone():
    # `/catalog/components/?service=` serves it, and three other
    # screens besides.
    service = ServiceFactory()
    response = APIClient().get(f"/catalog/services/{service.slug}/components/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_the_nested_event_route_is_gone():
    # `/events/?service=` serves it, beside every other event list.
    service = ServiceFactory()
    response = APIClient().get(f"/catalog/services/{service.slug}/events/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_a_service_still_answers_by_slug():
    # The service page reads it for the header and the About tab.
    service = ServiceFactory(name="Twilio")
    StatusPageFactory(service=service)
    response = APIClient().get(reverse("service-detail", args=[service.slug]))
    assert response.status_code == 200
    assert response.json()["name"] == "Twilio"
    # Nothing renders a description, so it is not in the shape.
    assert "description" not in response.json()


@pytest.mark.django_db
def test_every_list_response_uses_the_same_envelope():
    body = APIClient().get(reverse("component-list")).json()
    assert set(body) == {"aggregates", "next", "results"}
    assert "total" in body["aggregates"]


@pytest.mark.django_db
def test_a_service_nests_its_overall_component_rather_than_copying_its_fields():
    service = ServiceFactory(slug="twilio")
    StatusPageFactory(service=service)
    _with_status(service, Severity.MAJOR_OUTAGE, is_overall=True)
    body = _service_detail(service)
    assert body["overall_component"]["status"]["severity"] == Severity.MAJOR_OUTAGE
    assert "severity" not in body


@pytest.mark.django_db
def test_the_overall_component_is_a_plain_component():
    # One shape everywhere, so one renderer draws every row.
    service = ServiceFactory()
    StatusPageFactory(service=service)
    _with_status(service, Severity.OPERATIONAL, is_overall=True)
    overall = _service_detail(service)["overall_component"]
    for field in (
        "id",
        "name",
        "path",
        "parent",
        "descendant_count",
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
    # The contract's name is not a column. It points at an annotation,
    # and a filter that missed it would answer every row.
    service = ServiceFactory()
    StatusPageFactory(service=service)
    _with_status(service, Severity.MAJOR_OUTAGE, is_overall=True)
    _with_status(service, Severity.OPERATIONAL)
    url = reverse("component-list")
    assert len(APIClient().get(url).json()["results"]) == 2
    assert (
        len(APIClient().get(url, {"status__severity__lte": 3}).json()["results"]) == 1
    )


@pytest.mark.django_db
def test_fields_prunes_the_response():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    _with_status(service, Severity.OPERATIONAL, is_overall=True)
    url = reverse("service-detail", args=[service.slug])
    body = APIClient().get(url, {"fields": "id,name"}).json()
    assert set(body) == {"id", "name"}


@pytest.mark.django_db
def test_a_dotted_field_path_prunes_inside_a_nested_object():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    _with_status(service, Severity.OPERATIONAL, is_overall=True)
    url = reverse("service-detail", args=[service.slug])
    body = (
        APIClient().get(url, {"fields": "id,overall_component.status.severity"}).json()
    )
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
    overall = _service_detail(service)["overall_component"]
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
    overall = _service_detail(service)["overall_component"]
    assert overall["upcoming_maintenance"] is None
    assert overall["upcoming_maintenance_count"] == 0


@pytest.mark.django_db
def test_suggestions_put_what_is_broken_ahead_of_what_is_popular():
    """Severity sits ahead of popularity on purpose.

    A middling component that is broken now beats a popular one that is
    fine. That is the premise of the public view.
    """
    popular = ServiceFactory(name="Popular")
    StatusPageFactory(service=popular)
    watched = _with_status(popular, Severity.OPERATIONAL, is_overall=True)
    for _ in range(5):
        track(watched)

    broken = ServiceFactory(name="Broken")
    StatusPageFactory(service=broken)
    track(_with_status(broken, Severity.MAJOR_OUTAGE, is_overall=True))

    names = [
        r["service"]["name"]
        for r in APIClient().get(reverse("component-list")).json()["results"]
    ]
    assert names.index("Broken") < names.index("Popular")


@pytest.mark.django_db
def test_a_featured_component_still_leads():
    # Featured is the first key, ahead of severity. An editor's pick
    # leads even when something worse is on the same page.
    plain = ServiceFactory(name="Plain")
    StatusPageFactory(service=plain)
    _with_status(plain, Severity.MAJOR_OUTAGE, is_overall=True)

    featured = ServiceFactory(name="Featured")
    StatusPageFactory(service=featured)
    row = _with_status(featured, Severity.OPERATIONAL, is_overall=True)
    row.is_featured = True
    row.save(update_fields=["is_featured"])

    names = [
        r["service"]["name"]
        for r in APIClient().get(reverse("component-list")).json()["results"]
    ]
    assert names.index("Featured") < names.index("Plain")


@pytest.mark.django_db
def test_a_featured_leaf_leads_as_well_as_a_featured_rollup():
    # Discover lists every component, and the sort reads the flag on
    # every row. Featuring one part of a service surfaces that part.
    service = ServiceFactory(name="Twilio")
    StatusPageFactory(service=service)
    _with_status(service, Severity.MAJOR_OUTAGE, is_overall=True, external_id="roll")
    leaf = _with_status(service, Severity.OPERATIONAL, external_id="leaf")
    leaf.name = "SMS"
    leaf.is_featured = True
    leaf.save(update_fields=["name", "is_featured"])

    names = [
        r["name"] for r in APIClient().get(reverse("component-list")).json()["results"]
    ]
    assert names[0] == "SMS"


@pytest.mark.django_db
def test_a_component_with_no_reading_sorts_last_not_first():
    # Never seen is not the same as healthy, and it must not pose as
    # broken either.
    unread = ServiceFactory(name="Unread")
    StatusPageFactory(service=unread)
    ComponentFactory(service=unread, is_overall=True)

    healthy = ServiceFactory(name="Healthy")
    StatusPageFactory(service=healthy)
    _with_status(healthy, Severity.OPERATIONAL, is_overall=True)

    names = [
        r["service"]["name"]
        for r in APIClient().get(reverse("component-list")).json()["results"]
    ]
    assert names.index("Healthy") < names.index("Unread")


@pytest.mark.django_db
def test_a_path_carries_enough_to_link_to_each_step():
    # A joined string named the ancestors and gave a client nothing to
    # click. Each step is a row with its own id.
    from catalog.serializers import ComponentSerializer

    service = ServiceFactory(name="Twilio")
    overall = ComponentFactory(service=service, name="Twilio", is_overall=True)
    parent = ComponentFactory(
        service=service, name="Programmable Messaging", parent=overall
    )
    child = ComponentFactory(service=service, name="SMS", parent=parent)

    path = ComponentSerializer(child).data["path"]

    assert [step["name"] for step in path] == ["Twilio", "Programmable Messaging"]
    assert path[0]["id"] == str(overall.id)
    assert path[0]["is_overall"] is True
    # Empty, not null: the overall component is under nothing, and a
    # client maps over the list without checking first.
    assert ComponentSerializer(overall).data["path"] == []


@pytest.mark.django_db
def test_fields_prunes_inside_a_path_step():
    # `path` is a method field, so `_prune` cannot reach the step
    # serializer. A dotted path into it was ignored, and the contract
    # promises a dotted path prunes wherever it is accepted.
    service = ServiceFactory(name="Twilio")
    overall = ComponentFactory(service=service, name="Twilio", is_overall=True)
    child = ComponentFactory(service=service, name="SMS", parent=overall)

    url = reverse("component-detail", args=[child.id])
    body = APIClient().get(url, {"fields": "path.name"}).json()

    assert body["path"] == [{"name": "Twilio"}]


@pytest.mark.django_db
def test_fields_refuses_an_unknown_name_under_a_path_step():
    # Nothing pruned and nothing refused. A typo read as a step that
    # holds every field, which is the opposite of what was asked for.
    service = ServiceFactory(name="Twilio")
    overall = ComponentFactory(service=service, name="Twilio", is_overall=True)
    child = ComponentFactory(service=service, name="SMS", parent=overall)

    url = reverse("component-detail", args=[child.id])
    response = APIClient().get(url, {"fields": "path.nonsense"})

    assert response.status_code == 400
    assert response.json() == {"fields": ["Unknown field: nonsense."]}


@pytest.mark.django_db
def test_a_finished_maintenance_window_is_not_live():
    # A provider often leaves the phase behind when a window ends, so
    # the end matters as much as the phase.
    from datetime import timedelta

    from django.utils import timezone

    from status.choices import EventKind, MaintenancePhase
    from status.models import ServiceEvent

    service = ServiceFactory()
    now = timezone.now()
    common = {
        "service": service,
        "kind": EventKind.MAINTENANCE,
        "phase": MaintenancePhase.IN_PROGRESS,
        "starts_at": now - timedelta(hours=2),
    }
    ServiceEvent.objects.create(
        title="Over", external_id="over", ends_at=now - timedelta(hours=1), **common
    )
    running = ServiceEvent.objects.create(
        title="Running", external_id="running", ends_at=None, **common
    )

    live = ServiceEvent.objects.live(EventKind.MAINTENANCE)

    assert list(live) == [running]


@pytest.mark.django_db
def test_a_component_list_costs_the_same_whatever_its_length():
    # It answered seven fields with a query each, per row. A page of
    # fifty cost three hundred and fifty six.
    from django.db import connection, reset_queries
    from django.test import override_settings

    service = ServiceFactory()
    StatusPageFactory(service=service)
    for n in range(30):
        _with_status(service, Severity.DEGRADED, external_id=f"c{n}")

    counts = {}
    with override_settings(DEBUG=True):
        for size in (2, 30):
            reset_queries()
            APIClient().get(
                reverse("component-list"),
                {"service": service.slug, "page_size": size},
            )
            counts[size] = len(connection.queries)

    assert counts[2] == counts[30], counts
