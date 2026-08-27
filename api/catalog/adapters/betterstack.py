from catalog.adapters.base import Adapter
from catalog.choices import StatusPageProvider


class BetterStackAdapter(Adapter):
    """Better Stack. A later task fills this in."""

    provider = StatusPageProvider.BETTERSTACK

    @classmethod
    def matches(cls, url: str) -> bool:
        return "betterstack.com" in url

    def fetch_status(self):
        raise NotImplementedError

    def fetch_incidents(self):
        raise NotImplementedError

    def fetch_service_metadata(self):
        raise NotImplementedError
