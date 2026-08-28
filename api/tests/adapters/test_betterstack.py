import pytest

from polling.adapters.services.betterstack import BetterStackAdapter
from status.choices import Severity
from tests.adapters.conftest import StubSession


@pytest.fixture
def adapter(load):
    return BetterStackAdapter(
        "https://statuspage.betterstack.com/",
        session=StubSession({"index.json": load("betterstack_summary.json")}),
    )


def test_it_returns_exactly_one_overall_component(adapter):
    assert len([c for c in adapter.fetch_status() if c.is_overall]) == 1


def test_every_component_maps_onto_the_severity_scale(adapter):
    for component in adapter.fetch_status():
        assert component.severity in {s.value for s in Severity}


def test_it_returns_events(adapter):
    assert isinstance(adapter.fetch_incidents(), list)
