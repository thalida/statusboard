from catalog.adapters.base import Adapter
from catalog.choices import StatusPageProvider


class StatuspageAdapter(Adapter):
    """Atlassian Statuspage. A later task fills this in."""

    provider = StatusPageProvider.STATUSPAGE

    @classmethod
    def matches(cls, url: str) -> bool:
        # Instatus and Better Stack also use "status." subdomains.
        # Rule those out first so they stay on their own adapters.
        return (
            "instatus.com" not in url
            and "betterstack.com" not in url
            and ("status." in url or "githubstatus" in url or "statuspage.io" in url)
        )

    def fetch_status(self):
        raise NotImplementedError

    def fetch_incidents(self):
        raise NotImplementedError

    def fetch_service_metadata(self):
        raise NotImplementedError
