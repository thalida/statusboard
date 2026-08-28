from polling.adapters.base import Adapter
from polling.adapters.betterstack import BetterStackAdapter
from polling.adapters.instatus import InstatusAdapter
from polling.adapters.rss import RSSAdapter
from polling.adapters.statuspage import StatuspageAdapter

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
