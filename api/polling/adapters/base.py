from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


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


class Adapter(ABC):
    """One class per provider. One interface.

    Read a URL. Return normalised components and events.
    Nothing downstream knows the provider, so a new provider is one new class.
    """

    provider: str = ""

    # True for an adapter written for one company's page. Probing must
    # not offer these to a page they do not match: several read a path
    # that other platforms also serve, and would claim someone else's
    # page and report the wrong company's status on it.
    host_specific: bool = False

    def __init__(self, url: str, session=None):
        self.url = url
        self.session = session

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool: ...

    @abstractmethod
    def fetch_status(self) -> list[NormalisedComponent]: ...

    @abstractmethod
    def fetch_incidents(self) -> list[NormalisedEvent]: ...

    @abstractmethod
    def fetch_service_metadata(self) -> dict: ...

    def fetch_logo(self) -> str:
        """The product's own mark, scraped from the status page.

        No provider publishes one in its JSON, so this is the same for
        all of them. A provider that does can override it.
        """
        from polling.logo import find_logo

        return find_logo(self.url, self.session)
