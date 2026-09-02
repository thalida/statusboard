from urllib.parse import urljoin

from catalog.choices import StatusPageProvider
from polling.adapters.services.rss import RSSAdapter


class GoogleFeedAdapter(RSSAdapter):
    """Google's dashboards other than Cloud: Firebase and Workspace.

    Both render in the browser and advertise nothing, but both serve an
    Atom feed at a known path.
    """

    provider = StatusPageProvider.GOOGLE_FEED
    host_specific = True

    # The feed sits at a fixed path. Nothing in the markup links to it.
    FEED_PATH = "en/feed.atom"
    HOSTS = ("status.firebase.google.com", "google.com/appsstatus")

    @classmethod
    def matches(cls, url: str) -> bool:
        return any(host in url for host in cls.HOSTS)

    def get_feed(self):
        if self.matches(self.url) and not self.url.endswith(self.FEED_PATH):
            base = self.url if self.url.endswith("/") else self.url + "/"
            self.url = urljoin(base, self.FEED_PATH)
        return super().get_feed()
