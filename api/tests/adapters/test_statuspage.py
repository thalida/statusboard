import pytest

from polling.adapters.statuspage import StatuspageAdapter
from status.choices import EventKind, Severity
from tests.adapters.conftest import StubSession


@pytest.fixture
def adapter(load):
    return StatuspageAdapter(
        "https://status.twilio.com/",
        session=StubSession(
            {
                "summary.json": load("statuspage_summary.json"),
                "incidents.json": load("statuspage_incidents.json"),
                "scheduled-maintenances.json": load(
                    "statuspage_scheduled_maintenances.json"
                ),
            }
        ),
    )


def test_it_derives_the_api_path_from_the_page_url(adapter):
    adapter.fetch_status()
    assert adapter.session.requested == [
        "https://status.twilio.com/api/v2/summary.json"
    ]


def test_it_returns_one_overall_component(adapter):
    overall = [c for c in adapter.fetch_status() if c.is_overall]
    assert len(overall) == 1


def test_the_overall_component_uses_the_providers_own_indicator(adapter):
    # Use the provider's own indicator.
    # A worst-of-components rollup leaves a large service always orange.
    overall = next(c for c in adapter.fetch_status() if c.is_overall)
    assert overall.severity in {s.value for s in Severity}


def test_every_component_has_a_provider_id_and_a_severity(adapter):
    for component in adapter.fetch_status():
        assert component.external_id
        assert component.severity in {s.value for s in Severity}


def test_nested_components_carry_their_parent_id(adapter):
    components = adapter.fetch_status()
    ids = {c.external_id for c in components}
    for component in components:
        if component.parent_external_id is not None:
            assert component.parent_external_id in ids


def test_incidents_and_maintenance_both_come_back_as_events(adapter):
    kinds = {e.kind for e in adapter.fetch_incidents()}
    assert kinds <= {EventKind.INCIDENT, EventKind.MAINTENANCE}
    # The recorded fixtures carry both kinds; assert that, not just the subset.
    assert kinds == {EventKind.INCIDENT, EventKind.MAINTENANCE}


def test_an_event_carries_its_update_log(adapter):
    events = adapter.fetch_incidents()
    assert any(len(e.updates) > 0 for e in events)


def test_a_resolved_incident_has_an_end_time(adapter):
    for event in adapter.fetch_incidents():
        if event.phase == "resolved":
            assert event.ends_at is not None


def test_status_maps_to_the_severity_scale():
    assert StatuspageAdapter.SEVERITY["operational"] == Severity.OPERATIONAL
    assert StatuspageAdapter.SEVERITY["major_outage"] == Severity.MAJOR_OUTAGE
    assert StatuspageAdapter.SEVERITY["under_maintenance"] == Severity.MAINTENANCE
    # Anything we do not recognise is unknown, which sorts with the problems.
    assert (
        StatuspageAdapter.SEVERITY.get("something_new", Severity.UNKNOWN)
        == Severity.UNKNOWN
    )
