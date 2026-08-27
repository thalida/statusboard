from catalog.adapters.base import Adapter
from catalog.adapters.betterstack import BetterStackAdapter
from catalog.adapters.instatus import InstatusAdapter
from catalog.adapters.rss import RSSAdapter
from catalog.adapters.statuspage import StatuspageAdapter

# Order matters: RSS is last because it is the fallback, not a match.
ADAPTERS: tuple[type[Adapter], ...] = (
    StatuspageAdapter,
    InstatusAdapter,
    BetterStackAdapter,
)


def detect(url: str) -> type[Adapter]:
    """Return the adapter class for a status page URL.

    Falls back to RSSAdapter when no known provider matches.
    """
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter
    return RSSAdapter
