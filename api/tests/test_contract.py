from pathlib import Path

import pytest
import yaml
from django.urls import reverse
from drf_spectacular.drainage import GENERATOR_STATS, reset_generator_stats
from drf_spectacular.generators import SchemaGenerator

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

    from common.serializers import ERROR_CODES

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
        assert code in ERROR_CODES
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
    monkeypatch.setattr("polling.adapters.registry.identify", refuses)
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
    monkeypatch.setattr("polling.adapters.registry.identify", times_out)
    response = APIClient().post(
        reverse("catalog-import"),
        {"status_page_url": "https://status.example.com/"},
        format="json",
    )

    assert response.status_code == 502
    assert response.json()["code"] == "provider_unreachable"
