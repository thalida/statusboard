from pathlib import Path

import pytest
import yaml
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
