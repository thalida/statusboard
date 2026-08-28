from urllib.parse import urljoin

from catalog.choices import StatusPageProvider
from polling.adapters.services.rss import RSSAdapter

# Google's status dashboards publish a feed at a fixed path and link it
# nowhere the page's markup can be read from.
FEED_PATH = "en/feed.atom"

HOSTS = ("status.firebase.google.com", "google.com/appsstatus")


class GoogleFeedAdapter(RSSAdapter):
    """Google's dashboards other than Cloud: Firebase and Workspace.

    Both render in the browser and advertise nothing, but both serve an
    Atom feed at a known path.
    """

    provider = StatusPageProvider.GOOGLE_FEED
    host_specific = True

    @classmethod
    def matches(cls, url: str) -> bool:
        return any(host in url for host in HOSTS)

    def _feed(self):
        if self.matches(self.url) and not self.url.endswith(FEED_PATH):
            base = self.url if self.url.endswith("/") else self.url + "/"
            self.url = urljoin(base, FEED_PATH)
        return super()._feed()
