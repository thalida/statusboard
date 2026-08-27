from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests

from catalog.adapters.base import Adapter, NormalisedComponent, NormalisedEvent
from catalog.choices import StatusPageProvider
from status.choices import EventKind, IncidentPhase, MaintenancePhase, Severity


def _parse(value):
    """Parse an Instatus timestamp. Return None for a missing value."""
    return datetime.fromisoformat(value) if value else None


class InstatusAdapter(Adapter):
    """Instatus.

    Its public summary.json has no component or incident-update list.
    It has only a page-level status, active incidents, and active
    maintenance. fetch_status returns one overall component.
    """

    provider = StatusPageProvider.INSTATUS

    # Component and incident-impact vocabulary, per Instatus docs.
    # summary.json never lists components, but incident "impact" uses
    # this same scale.
    SEVERITY = {
        "OPERATIONAL": Severity.OPERATIONAL,
        "UNDERMAINTENANCE": Severity.MAINTENANCE,
        "DEGRADEDPERFORMANCE": Severity.DEGRADED,
        "MINOROUTAGE": Severity.PARTIAL_OUTAGE,
        "PARTIALOUTAGE": Severity.PARTIAL_OUTAGE,
        "MAJOROUTAGE": Severity.MAJOR_OUTAGE,
    }
    # The page-level status is a plain up/has-issues flag. It carries
    # no severity gradient, so "has issues" maps to one mid tier.
    INDICATOR = {
        "UP": Severity.OPERATIONAL,
        "HASISSUES": Severity.DEGRADED,
    }
    INCIDENT_PHASE = {
        "INVESTIGATING": IncidentPhase.INVESTIGATING,
        "IDENTIFIED": IncidentPhase.IDENTIFIED,
        "MONITORING": IncidentPhase.MONITORING,
        "RESOLVED": IncidentPhase.RESOLVED,
    }
    MAINTENANCE_PHASE = {
        "NOTSTARTEDYET": MaintenancePhase.SCHEDULED,
        "INPROGRESS": MaintenancePhase.IN_PROGRESS,
        "COMPLETED": MaintenancePhase.COMPLETED,
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "instatus.com" in url

    def _get(self, path):
        session = self.session or requests
        response = session.get(urljoin(self.url, path), timeout=10)
        response.raise_for_status()
        return response.json()

    def fetch_status(self):
        page = self._get("summary.json").get("page", {})
        # summary.json carries no component list, only the page's own
        # status. Return a single overall component built from it.
        return [
            NormalisedComponent(
                external_id="overall",
                name=page.get("name", "Overall status"),
                severity=self.INDICATOR.get(page.get("status"), Severity.UNKNOWN),
                is_overall=True,
                order=-1,
            )
        ]

    def _incident(self, raw):
        return NormalisedEvent(
            external_id=str(raw["id"]),
            kind=EventKind.INCIDENT,
            title=raw.get("name", ""),
            phase=self.INCIDENT_PHASE.get(
                raw.get("status"), IncidentPhase.INVESTIGATING
            ),
            starts_at=_parse(raw.get("started")),
        )

    def _maintenance(self, raw):
        starts_at = _parse(raw.get("start"))
        duration = raw.get("duration")
        ends_at = (
            starts_at + timedelta(minutes=duration) if starts_at and duration else None
        )
        return NormalisedEvent(
            external_id=str(raw["id"]),
            kind=EventKind.MAINTENANCE,
            title=raw.get("name", ""),
            phase=self.MAINTENANCE_PHASE.get(
                raw.get("status"), MaintenancePhase.SCHEDULED
            ),
            starts_at=starts_at,
            ends_at=ends_at,
        )

    def fetch_incidents(self):
        # Only active incidents and maintenance are public here. There
        # is no update log or affected-component list at this endpoint.
        body = self._get("summary.json")
        events = [self._incident(raw) for raw in body.get("activeIncidents", [])]
        events += [self._maintenance(raw) for raw in body.get("activeMaintenances", [])]
        return events

    def fetch_service_metadata(self):
        page = self._get("summary.json").get("page", {})
        return {"name": page.get("name", ""), "homepage_url": page.get("url", "")}
