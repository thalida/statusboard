from pathlib import Path

import pytest

from catalog.adapters.rss import RSSAdapter
from status.choices import EventKind, IncidentPhase, Severity, StatusSource

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class StubTextSession:
    """Return one recorded feed body. No network."""

    def __init__(self, text):
        self.text = text

    def get(self, url, **kwargs):
        return type(
            "R",
            (),
            {
                "text": self.text,
                "content": self.text.encode(),
                "status_code": 200,
                "raise_for_status": lambda self: None,
                "headers": {},
            },
        )()


@pytest.fixture
def adapter():
    return RSSAdapter(
        "https://www.githubstatus.com/history.rss",
        session=StubTextSession((FIXTURES / "rss_feed.xml").read_text()),
    )


def test_it_returns_exactly_one_component_and_it_is_the_overall_one(adapter):
    components = adapter.fetch_status()
    assert len(components) == 1
    assert components[0].is_overall is True


def test_the_synthetic_component_has_no_parent_and_no_children(adapter):
    component = adapter.fetch_status()[0]
    assert component.parent_external_id is None
    assert component.order == 0


def test_severity_is_operational_when_nothing_is_open(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "fetch_incidents", list)
    assert adapter.fetch_status()[0].severity == Severity.OPERATIONAL


def test_severity_is_degraded_while_an_incident_is_open(adapter, monkeypatch):
    from django.utils import timezone

    from catalog.adapters.base import NormalisedEvent

    monkeypatch.setattr(
        adapter,
        "fetch_incidents",
        lambda: [
            NormalisedEvent(
                external_id="1",
                kind=EventKind.INCIDENT,
                title="x",
                phase=IncidentPhase.INVESTIGATING,
                starts_at=timezone.now(),
                ends_at=None,
            )
        ],
    )
    # Degraded, not major: a feed tells us something is wrong, not how badly.
    assert adapter.fetch_status()[0].severity == Severity.DEGRADED


def test_it_declares_its_status_source_as_incidents(adapter):
    assert adapter.status_source == StatusSource.INCIDENTS


def test_it_returns_events_from_the_feed(adapter):
    events = adapter.fetch_incidents()
    assert len(events) > 0
    assert all(e.kind == EventKind.INCIDENT for e in events)


# The next four pin the resolution rule to the recorded payload. A feed
# entry's title never announces resolution — GitHub titles the entry for
# the fault ("Incident with Actions"). The phase marker is the first
# <strong> in the description, which is the newest update.


def test_no_entry_title_announces_resolution(adapter):
    # The guard against reintroducing a title-prefix heuristic.
    assert not any(
        e.title.lower().startswith("resolved") for e in adapter.fetch_incidents()
    )


def test_an_entry_whose_newest_update_is_resolved_reads_closed(adapter):
    event = next(
        e for e in adapter.fetch_incidents() if e.title == "Incident with Actions"
    )
    assert event.phase == IncidentPhase.RESOLVED
    assert event.ends_at is not None


def test_an_entry_still_being_updated_reads_open(adapter):
    event = next(
        e
        for e in adapter.fetch_incidents()
        if e.title == "Disruption with GitHub Billing"
    )
    assert event.phase != IncidentPhase.RESOLVED
    assert event.ends_at is None


def test_the_real_feed_exercises_both_directions(adapter):
    # Both branches come from the recorded payload, not a stub. If the
    # feed shape changes so one branch vanishes, this fails loudly.
    events = adapter.fetch_incidents()
    assert any(e.ends_at is None for e in events)
    assert any(e.ends_at is not None for e in events)


def test_service_metadata_comes_from_the_channel(adapter):
    assert adapter.fetch_service_metadata() == {
        "name": "GitHub Status - Incident History",
        "homepage_url": "https://www.githubstatus.com",
    }
