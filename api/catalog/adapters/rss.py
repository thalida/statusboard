from catalog.adapters.base import Adapter
from catalog.choices import StatusPageProvider


class RSSAdapter(Adapter):
    """Generic RSS feed. The fallback, not an error. A later task fills this in."""

    provider = StatusPageProvider.RSS

    @classmethod
    def matches(cls, url: str) -> bool:
        # The registry only reaches this adapter when nothing else matched.
        return True

    def fetch_status(self):
        raise NotImplementedError

    def fetch_incidents(self):
        raise NotImplementedError

    def fetch_service_metadata(self):
        raise NotImplementedError
