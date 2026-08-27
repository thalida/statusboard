from catalog.adapters.base import Adapter
from catalog.choices import StatusPageProvider


class InstatusAdapter(Adapter):
    """Instatus. A later task fills this in."""

    provider = StatusPageProvider.INSTATUS

    @classmethod
    def matches(cls, url: str) -> bool:
        return "instatus.com" in url

    def fetch_status(self):
        raise NotImplementedError

    def fetch_incidents(self):
        raise NotImplementedError

    def fetch_service_metadata(self):
        raise NotImplementedError
