from catalog.choices import StatusPageProvider
from polling.adapters.services.rss import RSSAdapter


class Auth0Adapter(RSSAdapter):
    """Auth0, whose status is per tenant.

    There is no feed for Auth0 as a whole. Every feed is scoped to one
    tenant. Nothing can be discovered from status.auth0.com alone, so
    the URL has to carry the tenant.

    This exists to say that. Without it the page fails like any
    unreadable one. The reason never reaches the person adding it, and
    only they know their tenant.
    """

    provider = StatusPageProvider.AUTH0
    host_specific = True

    HELP = (
        "Auth0 publishes a feed per tenant, not one for everyone. Use "
        "https://status.auth0.com/rss?domain=YOUR_TENANT.REGION.auth0.com "
        "as the status page URL."
    )

    @classmethod
    def matches(cls, url: str) -> bool:
        return "status.auth0.com" in url

    def _feed(self):
        if "domain=" not in self.url:
            raise ValueError(self.HELP)
        return super()._feed()
