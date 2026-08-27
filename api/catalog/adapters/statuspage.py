from datetime import datetime
from urllib.parse import urljoin

import requests

from catalog.adapters.base import (
    Adapter,
    NormalisedComponent,
    NormalisedEvent,
    NormalisedUpdate,
)
from catalog.choices import StatusPageProvider
from status.choices import EventKind, IncidentPhase, MaintenancePhase, Severity


def _parse(value):
    """Parse a Statuspage timestamp. Return None for a missing value."""
    return datetime.fromisoformat(value) if value else None


class StatuspageAdapter(Adapter):
    """Atlassian Statuspage. Covers most of the industry."""

    provider = StatusPageProvider.STATUSPAGE

    SEVERITY = {
        "operational": Severity.OPERATIONAL,
        "under_maintenance": Severity.MAINTENANCE,
        "degraded_performance": Severity.DEGRADED,
        "partial_outage": Severity.PARTIAL_OUTAGE,
        "major_outage": Severity.MAJOR_OUTAGE,
    }
    # The page-level indicator uses its own vocabulary, not a component status.
    INDICATOR = {
        "none": Severity.OPERATIONAL,
        "maintenance": Severity.MAINTENANCE,
        "minor": Severity.DEGRADED,
        "major": Severity.PARTIAL_OUTAGE,
        "critical": Severity.MAJOR_OUTAGE,
    }
    INCIDENT_PHASE = {
        "investigating": IncidentPhase.INVESTIGATING,
        "identified": IncidentPhase.IDENTIFIED,
        "monitoring": IncidentPhase.MONITORING,
        "resolved": IncidentPhase.RESOLVED,
        "postmortem": IncidentPhase.RESOLVED,
    }
    MAINTENANCE_PHASE = {
        "scheduled": MaintenancePhase.SCHEDULED,
        "in_progress": MaintenancePhase.IN_PROGRESS,
        "verifying": MaintenancePhase.VERIFYING,
        "completed": MaintenancePhase.COMPLETED,
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        # Instatus and Better Stack also use "status." subdomains.
        # Rule those out first so they stay on their own adapters.
        return (
            "instatus.com" not in url
            and "betterstack.com" not in url
            and ("status." in url or "githubstatus" in url or "statuspage.io" in url)
        )

    def _get(self, path):
        session = self.session or requests
        response = session.get(urljoin(self.url, path), timeout=10)
        response.raise_for_status()
        return response.json()

    def fetch_status(self):
        body = self._get("api/v2/summary.json")
        page = body.get("page", {})
        status = body.get("status", {})
        # Use the page's own indicator. Never derive the overall from
        # the worst component, or one bad component keeps it orange forever.
        components = [
            NormalisedComponent(
                external_id=str(page.get("id", "overall")),
                name=page.get("name", "Overall status"),
                severity=self.INDICATOR.get(status.get("indicator"), Severity.UNKNOWN),
                is_overall=True,
                order=-1,
            )
        ]
        for index, raw in enumerate(body.get("components", [])):
            components.append(
                NormalisedComponent(
                    external_id=str(raw["id"]),
                    name=raw.get("name", ""),
                    severity=self.SEVERITY.get(raw.get("status"), Severity.UNKNOWN),
                    parent_external_id=str(raw["group_id"])
                    if raw.get("group_id")
                    else None,
                    order=raw.get("position", index),
                )
            )
        return components

    def _event(self, raw, kind):
        phases = (
            self.INCIDENT_PHASE
            if kind == EventKind.INCIDENT
            else self.MAINTENANCE_PHASE
        )
        default = (
            IncidentPhase.INVESTIGATING
            if kind == EventKind.INCIDENT
            else MaintenancePhase.SCHEDULED
        )
        starts = (
            raw.get("scheduled_for")
            if kind == EventKind.MAINTENANCE
            else raw.get("started_at")
        ) or raw.get("created_at")
        ends = (
            raw.get("scheduled_until")
            if kind == EventKind.MAINTENANCE
            else raw.get("resolved_at")
        )
        return NormalisedEvent(
            external_id=str(raw["id"]),
            kind=kind,
            title=raw.get("name", ""),
            phase=phases.get(raw.get("status"), default),
            starts_at=_parse(starts),
            ends_at=_parse(ends),
            affected_external_ids=tuple(
                str(c["id"]) for c in raw.get("components", []) if c.get("id")
            ),
            updates=tuple(
                NormalisedUpdate(
                    phase=phases.get(u.get("status"), default),
                    body=u.get("body", ""),
                    posted_at=_parse(u.get("created_at")),
                )
                for u in raw.get("incident_updates", [])
            ),
        )

    def fetch_incidents(self):
        # Statuspage keeps maintenance on its own endpoint. incidents.json
        # never carries a scheduled_maintenances key, unlike summary.json.
        incidents = self._get("api/v2/incidents.json")
        maintenances = self._get("api/v2/scheduled-maintenances.json")
        events = [
            self._event(raw, EventKind.INCIDENT)
            for raw in incidents.get("incidents", [])
        ]
        events += [
            self._event(raw, EventKind.MAINTENANCE)
            for raw in maintenances.get("scheduled_maintenances", [])
        ]
        return events

    def fetch_service_metadata(self):
        page = self._get("api/v2/summary.json").get("page", {})
        return {"name": page.get("name", ""), "homepage_url": page.get("url", "")}
