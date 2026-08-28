import html
import logging
import re
from urllib.parse import urljoin

import requests

from polling.adapters.base import Adapter
from polling.adapters.services.betterstack import BetterStackAdapter
from polling.adapters.services.incidentio import IncidentIoAdapter
from polling.adapters.services.instatus import InstatusAdapter
from polling.adapters.services.rss import RSSAdapter
from polling.adapters.services.statuspage import StatuspageAdapter

# Order matters: RSS is last because it is the fallback, not a match.
ADAPTERS: tuple[type[Adapter], ...] = (
    IncidentIoAdapter,
    StatuspageAdapter,
    InstatusAdapter,
    BetterStackAdapter,
)

BY_PROVIDER = {adapter.provider: adapter for adapter in ADAPTERS}
BY_PROVIDER[RSSAdapter.provider] = RSSAdapter

# Where a page says its own feed is. Status pages that publish no API
# almost always advertise one of these, and often on another domain:
# status.notion.so points at notion-status.com, status.slack.com at
# slack-status.com.
FEED_LINK = re.compile(
    r"<link\b[^>]*?rel=[\"']alternate[\"'][^>]*>|<link\b[^>]*?type=[\"']application/"
    r"(?:rss|atom)\+xml[\"'][^>]*>",
    re.IGNORECASE,
)
FEED_TYPE = re.compile(r"application/(?:rss|atom)\+xml", re.IGNORECASE)
FEED_HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)

logger = logging.getLogger(__name__)


def detect(url: str) -> type[Adapter]:
    """The adapter a URL looks like it needs.

    A guess from the URL alone. `identify` checks it against the page.
    """
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter
    return RSSAdapter


def for_provider(provider: str) -> type[Adapter]:
    """The adapter for a provider already recorded on a StatusPage.

    A poll uses this rather than re-deciding. The decision was made once,
    against the live page, and a URL cannot see what `identify` saw.
    """
    return BY_PROVIDER.get(provider, RSSAdapter)


def identify(url: str, session=None) -> tuple[type[Adapter], str]:
    """Work out what a page actually serves, by asking it.

    Returns the adapter and the URL to use with it. Guessing from the URL
    is wrong often enough to matter: half the pages on a "status."
    subdomain are not Statuspage, and incident.io only serves the
    compatible API for some tenants.

    Raises if nothing can read the page. A status page we cannot parse
    has to fail loudly — the alternative is a service that shows green
    because nothing ever read it.
    """
    guess = detect(url)
    candidates = [guess] + [a for a in (*ADAPTERS, RSSAdapter) if a is not guess]

    for adapter_class in candidates:
        try:
            if adapter_class(url, session=session).fetch_status():
                return adapter_class, url
        except Exception as error:  # noqa: BLE001 — the next one may work
            logger.debug("%s could not read %s: %s", adapter_class.__name__, url, error)

    # No API. Ask the page where its feed is, which is how a page that
    # publishes nothing machine-readable still tells you.
    for feed_url in advertised_feeds(url, session):
        try:
            if RSSAdapter(feed_url, session=session).fetch_status():
                return RSSAdapter, feed_url
        except Exception as error:  # noqa: BLE001 — try the next feed
            logger.debug("no usable feed at %s: %s", feed_url, error)

    raise ValueError(f"No adapter could read {url}")


def advertised_feeds(url: str, session=None) -> list[str]:
    """The feeds a page links to, absolute and in document order.

    Often on another domain: status.notion.so points at
    notion-status.com, status.slack.com at slack-status.com.
    """
    try:
        markup = (session or requests).get(url, timeout=10).text
    except Exception as error:  # noqa: BLE001 — no page, no feeds
        logger.debug("could not read %s for feed links: %s", url, error)
        return []

    found = []
    for tag in FEED_LINK.findall(markup):
        if not FEED_TYPE.search(tag):
            continue
        href = FEED_HREF.search(tag)
        if href:
            candidate = urljoin(url, html.unescape(href.group(1)))
            if candidate not in found:
                found.append(candidate)
    return found
