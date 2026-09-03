import json
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
import requests

from catalog.choices import StatusPageProvider
from polling.adapters.base import Adapter, NormalisedComponent
from polling.adapters.registry import (
    RSSAdapter,
    _other_origins,
    advertised_feeds,
    detect,
    identify,
)
from polling.adapters.services.statuspage import StatuspageAdapter

# One resolved entry, which is all a feed needs to be readable.
ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Status</title>
  <entry>
    <title>TITLE</title>
    <updated>2026-08-01T00:00:00Z</updated>
    <id>urn:1</id>
    <content type="html">&lt;strong&gt;Resolved&lt;/strong&gt; all clear</content>
  </entry>
</feed>
"""


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


def test_no_adapter_answers_for_a_page_that_is_not_its_own():
    """Probing punishes an adapter that ignores its URL.

    One that answered regardless would claim every page nothing else
    could read. Its own provider's events would land under another
    service's name.
    """
    from polling.adapters.registry import ADAPTERS

    class Nothing:
        def get(self, url, **kwargs):
            raise OSError("not reachable")

    for adapter_class in ADAPTERS:
        adapter = adapter_class(
            "https://status.someone-else.example/", session=Nothing()
        )
        answered = None
        try:
            answered = adapter.fetch_status()
        except Exception as refusal:  # noqa: BLE001 — refusing is correct
            assert refusal is not None
        assert answered is None, f"{adapter_class.__name__} answered anyway"


def test_probing_never_offers_a_company_adapter_someone_elses_page():
    """The bug this guards against was live, twice.

    Several company adapters read a path other platforms also serve.
    Statuspage answers Oracle's api/v2/status.json.

    Tried against a foreign page, one claimed it. The wrong company's
    status was reported under that service's name.
    """
    from polling.adapters.registry import ADAPTERS, RSSAdapter, detect

    url = "https://status.someone-else.example/"
    guess = detect(url)
    offered = [guess] + [
        a for a in (*ADAPTERS, RSSAdapter) if a is not guess and not a.host_specific
    ]
    assert not [a for a in offered if a.host_specific], (
        "a company adapter was offered a page that is not that company's"
    )


def test_a_company_adapter_matches_only_its_own_company():
    # The flag keeps it out of the probe; matches() keeps it off pages
    # that are not its own. Both have to hold.
    from polling.adapters.registry import ADAPTERS

    for adapter_class in ADAPTERS:
        if not adapter_class.host_specific:
            continue
        assert not adapter_class.matches("https://status.someone-else.example/"), (
            f"{adapter_class.__name__} is host_specific and still claims a foreign page"
        )


class Page:
    """A fake session that answers a fixed map of URLs.

    `identify` is a ladder of fallbacks, and each rung is reached only
    when the one above it fails. So the way to test a rung is to decide
    what each URL answers.
    """

    def __init__(self, pages=None, feed_markup=""):
        self.pages = pages or {}
        self.feed_markup = feed_markup
        self.asked = []

    def get(self, url, **kwargs):
        self.asked.append(url)
        body = self.pages.get(url, self.feed_markup if url in self.pages else None)
        if body is None:
            raise requests.HTTPError(f"404 for {url}")
        return SimpleNamespace(
            text=body, json=lambda: json.loads(body), raise_for_status=lambda: None
        )


def test_a_page_that_answers_its_own_api_is_read_there():
    # The first rung: the adapter the URL suggests, at the URL given.
    page = Page(
        {
            "https://status.example.com/api/v2/summary.json": json.dumps(
                {"components": [{"id": "a", "name": "API", "status": "operational"}]}
            )
        }
    )

    adapter, url = identify("https://status.example.com/", session=page)

    assert adapter is StatuspageAdapter
    assert url == "https://status.example.com/"


def test_a_page_with_no_api_is_read_at_the_feed_it_advertises():
    # The second rung. A page that publishes nothing machine-readable
    # still names its feed in the markup, often on another host.
    feed = ATOM.replace("TITLE", "Investigating latency")
    page = Page(
        {
            "https://status.example.com/": (
                '<link rel="alternate" type="application/rss+xml" '
                'href="https://feeds.example.net/history.atom">'
            ),
            "https://feeds.example.net/history.atom": feed,
        }
    )

    adapter, url = identify("https://status.example.com/", session=page)

    assert adapter is RSSAdapter
    assert url == "https://feeds.example.net/history.atom"


def test_a_page_that_advertises_nothing_is_tried_where_feeds_live():
    # The third rung. A page that links to no feed often serves one.
    page = Page(
        {
            "https://status.example.com/": "<html>nothing here</html>",
            "https://status.example.com/history.rss": ATOM.replace("TITLE", "Down"),
        }
    )

    adapter, url = identify("https://status.example.com/", session=page)

    assert adapter is RSSAdapter
    assert url.endswith("/history.rss")


def test_a_page_that_moved_is_followed_to_the_host_it_names():
    # The fourth rung. intercomstatus.com links finstatus.com, whose
    # feed 404s while its API answers, so the host is worth a look.
    page = Page(
        {
            "https://status.example.com/": (
                '<link rel="alternate" type="application/atom+xml" '
                'href="https://moved.example.net/feed.atom">'
            ),
            "https://moved.example.net/api/v2/summary.json": json.dumps(
                {"components": [{"id": "a", "name": "API", "status": "operational"}]}
            ),
        }
    )

    adapter, url = identify("https://status.example.com/", session=page)

    assert adapter is StatuspageAdapter
    assert url == "https://moved.example.net/"


def test_nothing_readable_raises_rather_than_inventing_a_service():
    # A status page we cannot parse has to fail loudly. The alternative
    # is a service showing green because nothing read it.
    page = Page({"https://status.example.com/": "<html>not a status page</html>"})

    with pytest.raises(ValueError, match="No adapter could read"):
        identify("https://status.example.com/", session=page)


def test_a_host_specific_adapter_explains_why_it_could_not_read():
    # Auth0's reason is that only the person adding it knows their
    # tenant. That beats "nothing worked".
    page = Page({})

    with pytest.raises(ValueError) as raised:
        identify("https://status.auth0.com/", session=page)

    assert "tenant" in str(raised.value).lower()


def test_a_page_that_cannot_be_read_advertises_no_feeds():
    # No page, no feeds. It must not raise into the ladder above it.
    page = Page({})

    assert advertised_feeds("https://status.example.com/", session=page) == []


def test_only_a_feed_link_counts_as_a_feed():
    # A stylesheet is also a `link`. The type is what decides.
    markup = (
        '<link rel="alternate" type="text/html" href="/mirror">'
        '<link rel="alternate" type="application/rss+xml" href="/history.rss">'
    )
    page = Page({"https://status.example.com/": markup})

    found = advertised_feeds("https://status.example.com/", session=page)

    assert found == ["https://status.example.com/history.rss"]


def test_a_feed_on_this_host_is_not_another_origin():
    # Only a host the page pointed away to is worth a second look.
    here = "https://status.example.com/"
    feeds = [
        "https://status.example.com/history.rss",
        "https://www.status.example.com/other.rss",
        "https://elsewhere.example.net/feed.atom",
    ]

    assert _other_origins(here, feeds) == ["https://elsewhere.example.net/"]


def test_a_host_that_also_cannot_be_read_is_not_the_answer():
    # The last rung fails too, so the ladder ends where it began.
    page = Page(
        {
            "https://status.example.com/": (
                '<link rel="alternate" type="application/atom+xml" '
                'href="https://moved.example.net/feed.atom">'
            )
        }
    )

    with pytest.raises(ValueError, match="No adapter could read"):
        identify("https://status.example.com/", session=page)
