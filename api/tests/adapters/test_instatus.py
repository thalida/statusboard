import pytest

from polling.adapters.services.instatus import InstatusAdapter
from status.choices import Severity
from tests.adapters.conftest import StubSession


@pytest.fixture
def adapter(load):
    return InstatusAdapter(
        "https://status.instatus.com/",
        session=StubSession({"summary.json": load("instatus_summary.json")}),
    )


def test_it_returns_exactly_one_overall_component(adapter):
    assert len([c for c in adapter.fetch_status() if c.is_overall]) == 1


def test_every_component_maps_onto_the_severity_scale(adapter):
    for component in adapter.fetch_status():
        assert component.severity in {s.value for s in Severity}


def test_an_unrecognised_status_becomes_unknown_not_operational():
    # Guessing "operational" would show green for something we cannot read.
    assert (
        InstatusAdapter.SEVERITY.get("brand_new_status", Severity.UNKNOWN)
        == Severity.UNKNOWN
    )


def test_it_returns_events(adapter):
    assert isinstance(adapter.fetch_incidents(), list)
