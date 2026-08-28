import re
from datetime import UTC, datetime

import feedparser
import requests

from catalog.choices import StatusPageProvider
from polling.adapters.base import Adapter, NormalisedComponent, NormalisedEvent
from status.choices import EventKind, IncidentPhase, Severity, StatusSource

# A status feed writes its newest update first. Each update is led by a
# bolded phase word, such as "<strong>Resolved</strong>". So the first
# marker in the body is the entry's current phase.
PHASE_MARKER = re.compile(r"<strong>\s*(.*?)\s*</strong>", re.IGNORECASE | re.DOTALL)


class RSSAdapter(Adapter):
    """The fallback adapter.

    A feed has no component list. Severity comes from any open incident.
    `StatusSource.INCIDENTS` records this.
    """

    provider = StatusPageProvider.RSS
    status_source = StatusSource.INCIDENTS

    # The vocabulary Statuspage-backed feeds bold. "Update" is a progress
    # note with no phase of its own, so it leaves the entry open.
    PHASE = {
        "investigating": IncidentPhase.INVESTIGATING,
        "identified": IncidentPhase.IDENTIFIED,
        "monitoring": IncidentPhase.MONITORING,
        "resolved": IncidentPhase.RESOLVED,
        "completed": IncidentPhase.RESOLVED,
        "postmortem": IncidentPhase.RESOLVED,
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        # The registry only reaches this adapter when nothing else matched.
        return True

    def _feed(self):
        session = self.session or requests
        return feedparser.parse(session.get(self.url, timeout=10).text)

    def fetch_status(self):
        open_events = [e for e in self.fetch_incidents() if e.ends_at is None]
        return [
            NormalisedComponent(
                external_id="overall",
                name="Overall status",
                severity=Severity.DEGRADED if open_events else Severity.OPERATIONAL,
                parent_external_id=None,
                order=0,
                is_overall=True,
            )
        ]

    def _phase(self, description: str) -> str:
        """Read the entry's phase off its newest update.

        Never off the title. A feed titles an entry for the fault it
        describes, such as "Incident with Actions". It keeps that title
        after the entry resolves. Reading the title leaves every entry
        open. The service would then sit at DEGRADED forever.
        """
        match = PHASE_MARKER.search(description or "")
        if not match:
            return IncidentPhase.INVESTIGATING
        return self.PHASE.get(match.group(1).lower(), IncidentPhase.INVESTIGATING)

    def fetch_incidents(self):
        events = []
        for entry in self._feed().entries:
            published = entry.get("published_parsed")
            starts_at = datetime(*published[:6], tzinfo=UTC) if published else None
            phase = self._phase(entry.get("description", ""))
            resolved = phase == IncidentPhase.RESOLVED
            title = entry.get("title", "")
            events.append(
                NormalisedEvent(
                    external_id=entry.get("id") or entry.get("link") or title,
                    kind=EventKind.INCIDENT,
                    title=title,
                    phase=phase,
                    # A feed dates an entry by its newest update, so a
                    # resolved entry's pubDate is when it closed. That is
                    # the only end time on offer here.
                    starts_at=starts_at,
                    ends_at=starts_at if resolved else None,
                )
            )
        return events

    def fetch_service_metadata(self):
        feed = self._feed().feed
        return {"name": feed.get("title", ""), "homepage_url": feed.get("link", "")}
