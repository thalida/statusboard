from catalog.choices import StatusPageProvider
from polling.adapters.services.rss import RSSAdapter

FEED = "https://status.aws.amazon.com/rss/all.rss"


class AwsAdapter(RSSAdapter):
    """AWS, which publishes a feed and a page that cannot be read.

    health.aws.amazon.com is a JavaScript application: it links no feed
    and its JSON is UTF-16 and current-only. The feed at
    status.aws.amazon.com carries the same events, so the URL people
    paste is answered from there.
    """

    provider = StatusPageProvider.AWS

    @classmethod
    def matches(cls, url: str) -> bool:
        return "aws.amazon.com" in url and ("health" in url or "status" in url)

    def _feed(self):
        """Read AWS's feed, but only for an AWS URL.

        Probing tries every adapter against every page, so one that
        answered regardless of its URL would claim any page nothing else
        could read and report AWS's events under that service's name.
        """
        if self.matches(self.url):
            self.url = FEED
        return super()._feed()

    def fetch_service_metadata(self):
        return {
            "name": "Amazon Web Services",
            "homepage_url": "https://aws.amazon.com/",
        }
