from datetime import datetime
from urllib.parse import urljoin

from catalog.choices import StatusPageProvider
from polling import fetch
from polling.adapters.base import (
    Adapter,
    NormalisedComponent,
    NormalisedEvent,
    NormalisedUpdate,
)
from status.choices import EventKind, IncidentPhase, MaintenancePhase, Severity


def _parse(value):
    """Parse a Better Stack timestamp. Return None for a missing value."""
    return datetime.fromisoformat(value) if value else None


class BetterStackAdapter(Adapter):
    """Better Stack.

    index.json is a JSON:API document. Components and events live in
    a flat "included" array, sideloaded by type, not nested inline.
    """

    provider = StatusPageProvider.BETTERSTACK

    # A resource's own status. "not_monitored" is real but carries no
    # severity signal, so it is left out and falls through to unknown.
    SEVERITY = {
        "operational": Severity.OPERATIONAL,
        "degraded": Severity.DEGRADED,
        "downtime": Severity.MAJOR_OUTAGE,
        "maintenance": Severity.MAINTENANCE,
    }
    # The page-level indicator. Better Stack reuses the same words as
    # the resource scale, but a separate map keeps the two concepts apart.
    INDICATOR = {
        "operational": Severity.OPERATIONAL,
        "degraded": Severity.DEGRADED,
        "downtime": Severity.MAJOR_OUTAGE,
        "maintenance": Severity.MAINTENANCE,
    }
    # A status report's aggregate_state, once it closes.
    INCIDENT_PHASE = {
        "degraded": IncidentPhase.IDENTIFIED,
        "downtime": IncidentPhase.INVESTIGATING,
        "resolved": IncidentPhase.RESOLVED,
    }
    MAINTENANCE_PHASE = {
        "maintenance": MaintenancePhase.SCHEDULED,
        "resolved": MaintenancePhase.COMPLETED,
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "betterstack.com" in url

    def _get(self, path):
        session = self.session or fetch.session
        response = session.get(urljoin(self.url, path), timeout=10)
        response.raise_for_status()
        return response.json()

    def _included(self, body, kind):
        return [raw for raw in body.get("included", []) if raw.get("type") == kind]

    def fetch_status(self):
        body = self._get("index.json")
        data = body.get("data", {})
        attrs = data.get("attributes", {})
        # Use the page's own aggregate_state. Never derive the overall
        # from the worst resource, or one flaky monitor keeps it orange.
        components = [
            NormalisedComponent(
                external_id=str(data.get("id", "overall")),
                name=attrs.get("company_name", "Overall status"),
                severity=self.INDICATOR.get(
                    attrs.get("aggregate_state"), Severity.UNKNOWN
                ),
                is_overall=True,
                order=-1,
            )
        ]
        # Resources sit under sections, not under each other. A section
        # has no status of its own, so it is not a component here.
        for index, raw in enumerate(self._included(body, "status_page_resource")):
            raw_attrs = raw.get("attributes", {})
            components.append(
                NormalisedComponent(
                    external_id=str(raw["id"]),
                    name=raw_attrs.get("public_name", ""),
                    severity=self.SEVERITY.get(
                        raw_attrs.get("status"), Severity.UNKNOWN
                    ),
                    order=raw_attrs.get("position", index),
                )
            )
        return components

    def _event(self, raw, updates_by_id):
        attrs = raw.get("attributes", {})
        is_maintenance = attrs.get("report_type") == "maintenance"
        kind = EventKind.MAINTENANCE if is_maintenance else EventKind.INCIDENT
        phases = self.MAINTENANCE_PHASE if is_maintenance else self.INCIDENT_PHASE
        default = (
            MaintenancePhase.SCHEDULED
            if is_maintenance
            else IncidentPhase.INVESTIGATING
        )
        update_ids = [
            u["id"]
            for u in raw.get("relationships", {})
            .get("status_updates", {})
            .get("data", [])
        ]
        updates = []
        for update_id in update_ids:
            update = updates_by_id.get(update_id)
            if update is None:
                continue
            update_attrs = update.get("attributes", {})
            resource_status = next(
                (r.get("status") for r in update_attrs.get("affected_resources", [])),
                None,
            )
            updates.append(
                NormalisedUpdate(
                    phase=phases.get(resource_status, default),
                    body=update_attrs.get("message", ""),
                    posted_at=_parse(update_attrs.get("published_at")),
                )
            )
        return NormalisedEvent(
            external_id=str(raw["id"]),
            kind=kind,
            title=attrs.get("title", ""),
            phase=phases.get(attrs.get("aggregate_state"), default),
            starts_at=_parse(attrs.get("starts_at")),
            ends_at=_parse(attrs.get("ends_at")),
            affected_external_ids=tuple(
                str(r["status_page_resource_id"])
                for r in attrs.get("affected_resources", [])
                if r.get("status_page_resource_id")
            ),
            updates=tuple(updates),
        )

    def fetch_incidents(self):
        # Reports and their updates are both sideloaded here.
        # There is no separate incidents endpoint, unlike Statuspage.
        body = self._get("index.json")
        updates_by_id = {
            raw["id"]: raw for raw in self._included(body, "status_update")
        }
        return [
            self._event(raw, updates_by_id)
            for raw in self._included(body, "status_report")
        ]

    def fetch_service_metadata(self):
        attrs = self._get("index.json").get("data", {}).get("attributes", {})
        return {
            "name": attrs.get("company_name", ""),
            "homepage_url": attrs.get("company_url", ""),
        }
