from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlparse

from polling import fetch
from status.choices import StatusSource


@dataclass(frozen=True)
class NormalisedComponent:
    """A single status component, in provider-neutral form."""

    external_id: str
    name: str
    severity: int
    parent_external_id: str | None = None
    order: int = 0
    is_overall: bool = False


@dataclass(frozen=True)
class NormalisedUpdate:
    """One posted update on an event."""

    phase: str
    body: str
    posted_at: datetime


@dataclass(frozen=True)
class NormalisedEvent:
    """An incident or maintenance window, in provider-neutral form."""

    external_id: str
    kind: str
    title: str
    phase: str
    starts_at: datetime
    ends_at: datetime | None = None
    affected_external_ids: tuple[str, ...] = ()
    updates: tuple[NormalisedUpdate, ...] = field(default_factory=tuple)


def timestamp(value):
    """One provider timestamp, or None.

    Every provider writes ISO 8601 and one of them will write something
    else. A malformed date is not worth failing a whole poll over.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class Adapter(ABC):
    """One class per provider. One interface.

    Read a URL. Return normalised components and events.
    Nothing downstream knows the provider, so a new provider is one new class.
    """

    provider: str = ""

    # True for an adapter written for one company's page. Probing must
    # not offer these to a page they do not match.
    #
    # Several read a path other platforms also serve. One would claim
    # someone else's page and report the wrong company's status.
    host_specific: bool = False

    # Where a severity comes from. Most providers publish a component
    # list, and a feed-only page has to infer one from its incidents.
    # Two callers read this, and both used to spell the default out.
    status_source: str = StatusSource.PROVIDER

    # How long one request may wait. A slow page must not hold a worker.
    TIMEOUT = 15

    def __init__(self, url: str, session=None):
        self.url = url
        self.session = session

    @property
    def http(self):
        """The session to fetch with.

        The guarded one, unless a caller passed its own. A URL reaching
        here came from a person, so it is never ours to trust.
        """
        return self.session or fetch.session

    @property
    def base_url(self):
        """The page URL as a base.

        The trailing slash is what keeps the last segment. Without it
        `urljoin` replaces it, and a page under a path loses it.
        """
        return self.url if self.url.endswith("/") else self.url + "/"

    def get(self, path=""):
        """One response: the page itself, or a path under it.

        No path means the page as given. A feed URL names a file, and
        joining onto it would ask for a directory of that name.
        """
        url = urljoin(self.base_url, path) if path else self.url
        response = self.http.get(url, timeout=self.TIMEOUT)
        response.raise_for_status()
        return response

    def get_json(self, path=""):
        """The same, parsed."""
        return self.get(path).json()

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool: ...

    @abstractmethod
    def fetch_status(self) -> list[NormalisedComponent]: ...

    @abstractmethod
    def fetch_incidents(self) -> list[NormalisedEvent]: ...

    @abstractmethod
    def fetch_service_metadata(self) -> dict:
        """What the provider says the service is called, and where it is.

        Every key is optional. Half the providers publish no name, and
        one of those that does publishes it empty. `named_metadata` is
        what an importer wants.
        """

    def named_metadata(self) -> dict:
        """The same, with a name that is never blank.

        A service has to be called something the moment it is imported.
        The host is what somebody typed to get here.

        A poll reads `fetch_service_metadata` instead. There the old name
        is the better fallback. A host would overwrite a real name every
        time a provider answered without one.
        """
        metadata = dict(self.fetch_service_metadata())
        if not metadata.get("name"):
            metadata["name"] = urlparse(self.url).netloc
        return metadata

    def fetch_logo(self) -> str:
        """The product's own mark, scraped from the status page.

        No provider publishes one in its JSON, so this is the same for
        all of them. A provider that does can override it.
        """
        from polling.logo import find_logo

        return find_logo(self.url, self.session)
