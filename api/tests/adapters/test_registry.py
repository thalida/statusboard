from dataclasses import FrozenInstanceError

import pytest

from catalog.choices import StatusPageProvider
from polling.adapters.base import Adapter, NormalisedComponent
from polling.adapters.registry import detect


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://status.twilio.com/", StatusPageProvider.STATUSPAGE),
        ("https://www.githubstatus.com/", StatusPageProvider.STATUSPAGE),
        ("https://status.instatus.com/", StatusPageProvider.INSTATUS),
        ("https://statuspage.betterstack.com/", StatusPageProvider.BETTERSTACK),
        ("https://example.com/feed.xml", StatusPageProvider.RSS),
    ],
)
def test_detect_picks_the_provider_from_the_url(url, expected):
    assert detect(url).provider == expected


def test_anything_unrecognised_falls_back_to_rss():
    # RSS is the fallback, not an error. A feed is still data.
    assert detect("https://weird.example.org/status").provider == StatusPageProvider.RSS


def test_every_adapter_implements_the_same_interface():
    for method in (
        "fetch_status",
        "fetch_incidents",
        "fetch_service_metadata",
        "matches",
    ):
        assert hasattr(Adapter, method)


def test_normalised_component_is_immutable():
    component = NormalisedComponent(
        external_id="a",
        name="SMS",
        severity=5,
        parent_external_id=None,
        order=0,
        is_overall=False,
    )
    with pytest.raises(FrozenInstanceError):
        component.name = "changed"


def test_a_poll_uses_the_provider_recorded_at_import():
    # The decision was made once, against the live page. A URL cannot see
    # what identify saw, so re-deciding every poll would throw it away.
    from polling.adapters.registry import for_provider
    from polling.adapters.services.incidentio import IncidentIoAdapter
    from polling.adapters.services.rss import RSSAdapter

    assert for_provider("incident_io") is IncidentIoAdapter
    assert for_provider("rss") is RSSAdapter
    assert for_provider("something_new") is RSSAdapter


def test_feed_links_are_found_wherever_the_page_points():
    """Status pages often host their feed on another domain.

    status.notion.so points at notion-status.com, status.slack.com at
    slack-status.com. Guessing paths on the original host finds neither.
    """
    from polling.adapters.registry import advertised_feeds

    class StubPage:
        def get(self, url, **kwargs):
            markup = (
                '<link rel="alternate" type="application/rss+xml" '
                'href="https://elsewhere.example/feed.rss">'
                '<link rel="alternate" type="application/atom+xml" href="/local.atom">'
                '<link rel="stylesheet" href="/ignored.css">'
            )
            return type("R", (), {"text": markup})()

    assert advertised_feeds("https://status.example.com/", session=StubPage()) == [
        "https://elsewhere.example/feed.rss",
        "https://status.example.com/local.atom",
    ]


def test_a_page_nothing_can_read_is_refused():
    # Better than inventing a reading. A service that shows green because
    # nothing could read it is the failure worth avoiding.
    import pytest

    from polling.adapters.registry import identify

    class Broken:
        def get(self, url, **kwargs):
            raise OSError("down")

    with pytest.raises(ValueError, match="No adapter could read"):
        identify("https://nope.example.com/", session=Broken())
