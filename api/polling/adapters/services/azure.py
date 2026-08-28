from catalog.choices import StatusPageProvider
from polling.adapters.services.rss import RSSAdapter

FEED = "https://rssfeed.azure.status.microsoft/en-us/status/feed/"


class AzureAdapter(RSSAdapter):
    """Azure, whose page is an application and whose feed is elsewhere.

    azure.status.microsoft renders in the browser and links no feed that
    autodiscovery can see. The feed lives on its own host and carries the
    same events.
    """

    provider = StatusPageProvider.AZURE
    host_specific = True

    @classmethod
    def matches(cls, url: str) -> bool:
        return "azure.status.microsoft" in url or "azure.microsoft.com/status" in url

    def _feed(self):
        if self.matches(self.url):
            self.url = FEED
        return super()._feed()

    def fetch_service_metadata(self):
        return {
            "name": "Microsoft Azure",
            "homepage_url": "https://azure.microsoft.com/",
        }
