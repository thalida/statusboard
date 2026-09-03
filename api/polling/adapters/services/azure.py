from catalog.choices import StatusPageProvider
from polling.adapters.services.rss import RSSAdapter


class AzureAdapter(RSSAdapter):
    """Azure, whose page is an application and whose feed is elsewhere.

    azure.status.microsoft renders in the browser and links no feed that
    autodiscovery can see. The feed lives on its own host and carries the
    same events.
    """

    provider = StatusPageProvider.AZURE
    host_specific = True

    FEED = "https://rssfeed.azure.status.microsoft/en-us/status/feed/"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "azure.status.microsoft" in url or "azure.microsoft.com/status" in url

    def get_feed(self):
        if self.matches(self.url):
            self.url = self.FEED
        return super().get_feed()

    def fetch_service_metadata(self):
        return {
            "name": "Microsoft Azure",
            "homepage_url": "https://azure.microsoft.com/",
        }
