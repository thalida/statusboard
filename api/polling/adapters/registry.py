import html
import logging
import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests

from polling.adapters.base import Adapter
from polling.adapters.services.apple import AppleAdapter
from polling.adapters.services.aws import AwsAdapter
from polling.adapters.services.azure import AzureAdapter
from polling.adapters.services.betterstack import BetterStackAdapter
from polling.adapters.services.googlecloud import GoogleCloudAdapter
from polling.adapters.services.googlefeed import GoogleFeedAdapter
from polling.adapters.services.incidentio import IncidentIoAdapter
from polling.adapters.services.instatus import InstatusAdapter
from polling.adapters.services.oracle import OracleAdapter
from polling.adapters.services.rss import RSSAdapter
from polling.adapters.services.statusio import StatusIoAdapter
from polling.adapters.services.statuspage import StatuspageAdapter

# Order matters: RSS is last because it is the fallback, not a match.
ADAPTERS: tuple[type[Adapter], ...] = (
    AppleAdapter,
    AwsAdapter,
    AzureAdapter,
    GoogleCloudAdapter,
    GoogleFeedAdapter,
    OracleAdapter,
    IncidentIoAdapter,
    StatuspageAdapter,
    InstatusAdapter,
    BetterStackAdapter,
    # Last of the real adapters: it has no URL to match on, so it is
    # only ever reached by probing.
    StatusIoAdapter,
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
    # Everything else offered to a page is a general platform. A
    # company-specific adapter is only tried when the URL is that
    # company's, because several read a path other platforms also serve.
    general = [
        a for a in (*ADAPTERS, RSSAdapter) if a is not guess and not a.host_specific
    ]
    candidates = [guess, *general]

    for adapter_class in candidates:
        try:
            if adapter_class(url, session=session).fetch_status():
                return adapter_class, url
        except Exception as error:  # noqa: BLE001 — the next one may work
            logger.debug("%s could not read %s: %s", adapter_class.__name__, url, error)

    # No API. Ask the page where its feed is, which is how a page that
    # publishes nothing machine-readable still tells you.
    feeds = advertised_feeds(url, session)
    for feed_url in feeds:
        try:
            if RSSAdapter(feed_url, session=session).fetch_status():
                return RSSAdapter, feed_url
        except Exception as error:  # noqa: BLE001 — try the next feed
            logger.debug("no usable feed at %s: %s", feed_url, error)

    # A page that points at another host has usually moved there.
    # intercomstatus.com links finstatus.com, whose own feed 404s while
    # its API answers, so the host is worth a proper look and not just
    # the file it named.
    for origin in _other_origins(url, feeds):
        for adapter_class in candidates:
            try:
                if adapter_class(origin, session=session).fetch_status():
                    return adapter_class, origin
            except Exception as error:  # noqa: BLE001 — try the next one
                logger.debug("%s could not read %s: %s", adapter_class, origin, error)

    raise ValueError(f"No adapter could read {url}")


def _other_origins(url: str, feeds: list[str]) -> list[str]:
    """Hosts a page pointed at that are not its own, in order."""
    here = urlparse(url).netloc.lower().removeprefix("www.")
    seen, out = set(), []
    for feed in feeds:
        parts = urlparse(feed)
        host = parts.netloc.lower().removeprefix("www.")
        if host and host != here and host not in seen:
            seen.add(host)
            out.append(urlunparse((parts.scheme, parts.netloc, "/", "", "", "")))
    return out


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
