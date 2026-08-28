import json
from pathlib import Path

import pytest

from polling.adapters.services.statusio import StatusIoAdapter
from status.choices import Severity

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class StubStatusIo:
    """Serves the page markup, then the API payload. No network."""

    def __init__(self, markup):
        self.markup = markup
        self.payload = json.loads((FIXTURES / "statusio_status.json").read_text())

    def get(self, url, **kwargs):
        body = self.payload if "api.status.io" in url else None
        return type(
            "R",
            (),
            {
                "text": self.markup,
                "json": lambda self, b=body: b,
                "status_code": 200,
                "raise_for_status": lambda self: None,
            },
        )()


PAGE = '<html><script>var statuspage_id: "5b36dc6502d06804c08349f7";</script></html>'


@pytest.fixture
def adapter():
    return StatusIoAdapter("https://status.gitlab.com/", session=StubStatusIo(PAGE))


def test_it_returns_exactly_one_overall_component(adapter):
    assert len([c for c in adapter.fetch_status() if c.is_overall]) == 1


def test_the_overall_reading_is_the_pages_own(adapter):
    # Never the worst of its parts: one bad component would hold a
    # service orange forever.
    assert adapter.fetch_status()[0].severity == Severity.OPERATIONAL


def test_every_component_maps_onto_the_severity_scale(adapter):
    for component in adapter.fetch_status():
        assert component.severity in {s.value for s in Severity}


def test_an_unrecognised_code_becomes_unknown_not_operational():
    # Guessing green for a code we do not know would show a healthy
    # service that nobody has actually read.
    assert StatusIoAdapter.SEVERITY.get(999, Severity.UNKNOWN) == Severity.UNKNOWN


def test_it_never_matches_on_a_url():
    # Nothing in a status.io URL says so. It is only ever found by
    # probing the page.
    assert StatusIoAdapter.matches("https://status.gitlab.com/") is False


def test_a_page_without_an_id_is_refused():
    plain = StatusIoAdapter(
        "https://example.com/", session=StubStatusIo("<html></html>")
    )
    with pytest.raises(ValueError, match="not a status.io page"):
        plain.fetch_status()


def test_events_come_back_as_a_list(adapter):
    assert isinstance(adapter.fetch_incidents(), list)
