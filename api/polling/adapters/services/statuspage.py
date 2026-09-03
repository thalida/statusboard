import requests

from catalog.choices import StatusPageProvider
from polling.adapters.base import (
    Adapter,
    NormalisedComponent,
    NormalisedEvent,
    NormalisedUpdate,
    timestamp,
)
from status.choices import EventKind, IncidentPhase, MaintenancePhase, Severity


class StatuspageAdapter(Adapter):
    """Atlassian Statuspage. Covers most of the industry."""

    provider = StatusPageProvider.STATUSPAGE
    TIMEOUT = 10

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
        # Instatus, Better Stack and incident.io also use "status."
        # subdomains. Rule those out so they keep their own adapters.
        return (
            "instatus.com" not in url
            and "betterstack.com" not in url
            and "incident.io" not in url
            and ("status." in url or "githubstatus" in url or "statuspage.io" in url)
        )

    def fetch_status(self):
        body = self.get_json("api/v2/summary.json")
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
            starts_at=timestamp(starts),
            ends_at=timestamp(ends),
            affected_external_ids=tuple(
                str(c["id"]) for c in raw.get("components", []) if c.get("id")
            ),
            updates=tuple(
                NormalisedUpdate(
                    phase=phases.get(u.get("status"), default),
                    body=u.get("body", ""),
                    posted_at=timestamp(u.get("created_at")),
                )
                for u in raw.get("incident_updates", [])
            ),
        )

    def _maintenances(self):
        """Statuspage keeps maintenance on its own endpoint.

        incidents.json never carries a scheduled_maintenances key,
        unlike summary.json. Some compatible pages answer 404 here, such
        as incident.io on a custom domain.

        A provider with no maintenance to report is not a failed poll.
        That is an empty list, not an error.
        """
        try:
            return self.get_json("api/v2/scheduled-maintenances.json").get(
                "scheduled_maintenances", []
            )
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return []
            raise

    def fetch_incidents(self):
        incidents = self.get_json("api/v2/incidents.json")
        events = [
            self._event(raw, EventKind.INCIDENT)
            for raw in incidents.get("incidents", [])
        ]
        events += [
            self._event(raw, EventKind.MAINTENANCE) for raw in self._maintenances()
        ]
        return events

    def fetch_service_metadata(self):
        page = self.get_json("api/v2/summary.json").get("page", {})
        return {"name": page.get("name", ""), "homepage_url": page.get("url", "")}
