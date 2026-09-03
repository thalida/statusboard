from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.drainage import GENERATOR_STATS, reset_generator_stats
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.models import User
from dashboards.models import DashboardItem
from status.choices import EventKind, IncidentPhase
from status.models import ServiceEvent
from tests.factories import ComponentFactory, ServiceFactory, StatusPageFactory

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"


@pytest.fixture(scope="module")
def committed():
    return yaml.safe_load(CONTRACT.read_text())


@pytest.fixture
def generated():
    return SchemaGenerator().get_schema(request=None, public=True)


def _paths(schema):
    return {
        f"{verb.upper()} {path}"
        for path, ops in schema["paths"].items()
        for verb in ops
        if verb in ("get", "post", "delete", "patch", "put")
    }


def test_every_documented_operation_exists_in_the_code(committed, generated):
    missing = _paths(committed) - _paths(generated)
    assert not missing, f"documented but not implemented: {sorted(missing)}"


def test_no_operation_exists_that_the_contract_does_not_document(committed, generated):
    extra = _paths(generated) - _paths(committed)
    assert not extra, f"implemented but undocumented: {sorted(extra)}"


def test_every_endpoint_accepts_the_fields_parameter(generated):
    # ?fields= is baked in at the base layer, so it must appear on every
    # operation without a per-view annotation.
    for path, ops in generated["paths"].items():
        for verb, op in ops.items():
            if verb != "get":
                continue
            names = {p["name"] for p in op.get("parameters", [])}
            assert "fields" in names, f"{verb.upper()} {path} does not accept ?fields="


def _authed_client():
    """A client bearing a fresh user's access token."""
    user = User.objects.create(
        email=f"fields-probe-{User.objects.count()}@example.test"
    )
    api = APIClient()
    api.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
    )
    return api, user


def _meta_probe():
    return APIClient(), reverse("meta"), "max_page_size"


def _me_probe():
    api, _user = _authed_client()
    return api, reverse("me"), "email"


def _service_list_probe():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    ComponentFactory(service=service, is_overall=True)
    return APIClient(), reverse("service-list"), "id"


def _service_detail_probe():
    service = ServiceFactory()
    StatusPageFactory(service=service)
    ComponentFactory(service=service, is_overall=True)
    return APIClient(), reverse("service-detail", kwargs={"slug": service.slug}), "id"


def _service_components_probe():
    service = ServiceFactory()
    ComponentFactory(service=service, is_overall=True)
    url = reverse("service-components", kwargs={"slug": service.slug})
    return APIClient(), url, "id"


def _service_events_probe():
    service = ServiceFactory()
    ServiceEvent.objects.create(
        service=service,
        external_id="probe",
        kind=EventKind.INCIDENT,
        title="x",
        phase=IncidentPhase.DETECTED,
        starts_at=timezone.now(),
    )
    url = reverse("service-events", kwargs={"slug": service.slug})
    return APIClient(), url, "id"


def _component_list_probe():
    service = ServiceFactory()
    ComponentFactory(service=service, is_overall=True)
    return APIClient(), reverse("component-list"), "id"


def _component_detail_probe():
    service = ServiceFactory()
    component = ComponentFactory(service=service, is_overall=True)
    url = reverse("component-detail", kwargs={"uuid": component.id})
    return APIClient(), url, "id"


def _board_components_probe():
    api, user = _authed_client()
    board = user.default_dashboard
    service = ServiceFactory()
    component = ComponentFactory(service=service, is_overall=True)
    DashboardItem.objects.create(dashboard=board, component=component)
    url = reverse("board-components", kwargs={"uuid": board.id})
    return api, url, "id"


# One builder per documented GET path: a client, a live URL, and a field
# to keep. `/events/` and its children are not here. They are not in
# the contract yet, so this test does not cover them until they land.
FIELDS_PROBES = {
    "/meta/": _meta_probe,
    "/me/": _me_probe,
    "/catalog/services/": _service_list_probe,
    "/catalog/services/{slug}/": _service_detail_probe,
    "/catalog/services/{slug}/components/": _service_components_probe,
    "/catalog/services/{slug}/events/": _service_events_probe,
    "/catalog/components/": _component_list_probe,
    "/catalog/components/{uuid}/": _component_detail_probe,
    "/dashboards/{uuid}/components/": _board_components_probe,
}


def test_the_fields_probes_cover_every_documented_get(committed):
    # A GET added later and left out here would ship unpruned and
    # nothing would say so, the way /meta/ did.
    documented = {path for path, ops in committed["paths"].items() if "get" in ops}
    assert documented == set(FIELDS_PROBES)


@pytest.mark.django_db
@pytest.mark.parametrize("path", sorted(FIELDS_PROBES))
def test_fields_prunes_the_response(path):
    # Declaring ?fields= on a view is not the same as honouring it.
    # /meta/ built its body by hand and never ran it through the
    # serializer that prunes, so the parameter did nothing.
    client, url, field = FIELDS_PROBES[path]()
    body = client.get(url, {"fields": field}).json()
    kept = body["results"][0] if isinstance(body, dict) and "results" in body else body
    assert set(kept) == {field}, f"GET {path} ignored ?fields=: {sorted(kept)}"


@pytest.mark.django_db
def test_the_component_schema_has_exactly_the_documented_fields(committed):
    from catalog.serializers import ComponentSerializer

    documented = set(committed["components"]["schemas"]["Component"]["properties"])
    assert set(ComponentSerializer().fields) == documented


@pytest.mark.django_db
def test_the_service_schema_has_exactly_the_documented_fields(committed):
    from catalog.serializers import ServiceSerializer

    documented = set(committed["components"]["schemas"]["Service"]["properties"])
    assert set(ServiceSerializer().fields) == documented


@pytest.mark.django_db
def test_the_event_schema_has_exactly_the_documented_fields(committed):
    from status.serializers import ServiceEventSerializer

    documented = set(committed["components"]["schemas"]["ServiceEvent"]["properties"])
    assert set(ServiceEventSerializer().fields) == documented


@pytest.mark.django_db
def test_there_is_no_refresh_endpoint(generated):
    # A page load reads stored state. Reintroducing a manual refresh means
    # revisiting the spec, not adding a route.
    assert not [
        p for p in generated["paths"] if p.endswith("/refresh/") and "auth" not in p
    ]


def test_the_schema_generates_without_a_single_warning():
    """A warning means the schema is guessing.

    Each was a field typed `string` that is really an object or an
    integer. Or a view dropped from the schema entirely. A client is
    generated from this file, so a guess ships as a bug.
    """
    reset_generator_stats()
    with GENERATOR_STATS.silence():
        SchemaGenerator().get_schema(request=None, public=True)
    complaints = sorted(GENERATOR_STATS._warn_cache) + sorted(
        GENERATOR_STATS._error_cache
    )
    reset_generator_stats()
    assert not complaints, "\n".join(complaints)


@pytest.mark.django_db
def test_every_named_failure_answers_in_the_documented_shape():
    # `ErrorSerializer` and its codes were declared, documented, and
    # raised by nothing. Three different shapes came back instead.
    from rest_framework.test import APIClient

    from common.serializers import ErrorCode

    caller = APIClient()
    seen = {}

    missing = caller.get(reverse("service-detail", kwargs={"slug": "nope"}))
    seen["not_found"] = missing

    bad_token = caller.post(reverse("verify"), {"token": "no"}, format="json")
    seen["invalid_or_expired_token"] = bad_token

    for _ in range(8):
        throttled = caller.post(
            reverse("magic-link"), {"email": "shape@example.com"}, format="json"
        )
    seen["throttled"] = throttled

    for code, response in seen.items():
        body = response.json()
        assert body["code"] == code, f"{code} answered {body}"
        assert body["detail"], f"{code} carries no detail"
        assert set(body) == {"code", "detail"}
        assert code in set(ErrorCode)
    assert seen["throttled"].headers["Retry-After"]


@pytest.mark.django_db
def test_a_page_nothing_can_read_is_not_a_server_error(monkeypatch):
    # `identify` raises when no adapter could read the page. That is the
    # ordinary outcome of pasting the wrong address, and it used to
    # reach the caller as a 500.
    from rest_framework.test import APIClient

    def refuses(url, session=None):
        raise ValueError(f"No adapter could read {url}")

    # The address guard is not what is under test. It would resolve a
    # name the suite has no network for.
    monkeypatch.setattr("polling.fetch.check", lambda url: url)
    monkeypatch.setattr("polling.importer.identify", refuses)
    response = APIClient().post(
        reverse("catalog-import"),
        {"status_page_url": "https://status.example.com/"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "no_status_page_found"


@pytest.mark.django_db
def test_a_provider_that_will_not_answer_is_named_as_such(monkeypatch):
    import requests
    from rest_framework.test import APIClient

    def times_out(url, session=None):
        raise requests.ConnectTimeout("took too long")

    monkeypatch.setattr("polling.fetch.check", lambda url: url)
    monkeypatch.setattr("polling.importer.identify", times_out)
    response = APIClient().post(
        reverse("catalog-import"),
        {"status_page_url": "https://status.example.com/"},
        format="json",
    )

    assert response.status_code == 502
    assert response.json()["code"] == "provider_unreachable"
