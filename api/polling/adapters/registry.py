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


def detect(url: str) -> type[Adapter]:
    """Return the adapter class for a status page URL.

    Falls back to RSSAdapter when no known provider matches.
    """
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter
    return RSSAdapter
