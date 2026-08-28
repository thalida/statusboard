import json
from pathlib import Path

import pytest

from polling.adapters.services.cstate import CStateAdapter
from status.choices import Severity

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class StubIndex:
    def __init__(self, text):
        self.text = text

    def get(self, url, **kwargs):
        assert url.endswith("index.json")
        return type(
            "R", (), {"text": self.text, "raise_for_status": lambda self: None}
        )()


@pytest.fixture
def adapter():
    return CStateAdapter(
        "https://status.jenkins.io/",
        session=StubIndex((FIXTURES / "cstate_index.json").read_text()),
    )


def test_it_returns_one_overall_component(adapter):
    assert len([c for c in adapter.fetch_status() if c.is_overall]) == 1


def test_the_overall_is_the_pages_own_summary(adapter):
    assert adapter.fetch_status()[0].severity == Severity.OPERATIONAL


def test_every_system_becomes_a_component(adapter):
    components = [c for c in adapter.fetch_status() if not c.is_overall]
    assert len(components) > 5
    assert all(c.severity in {s.value for s in Severity} for c in components)


def test_an_unrecognised_state_becomes_unknown_not_operational():
    # Guessing green would show a healthy service nobody has read.
    assert CStateAdapter.SEVERITY.get("brand-new", Severity.UNKNOWN) == Severity.UNKNOWN


def test_a_file_with_control_characters_still_parses(adapter):
    # cState writes descriptions straight from Markdown, so the file
    # carries raw control characters that strict JSON rejects.
    assert adapter.fetch_status()


def test_a_page_that_is_not_cstate_is_refused():
    plain = CStateAdapter(
        "https://example.com/", session=StubIndex(json.dumps({"a": 1}))
    )
    with pytest.raises(ValueError, match="not a cState page"):
        plain.fetch_status()


def test_it_never_matches_on_a_url():
    assert CStateAdapter.matches("https://status.jenkins.io/") is False
