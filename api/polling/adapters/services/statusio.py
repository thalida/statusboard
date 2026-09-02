import re

from catalog.choices import StatusPageProvider
from polling.adapters.base import (
    Adapter,
    NormalisedComponent,
    NormalisedEvent,
    timestamp,
)
from status.choices import EventKind, IncidentPhase, MaintenancePhase, Severity


class StatusIoAdapter(Adapter):
    """status.io, used by GitLab and Databricks among others.

    One request carries everything: the page-level reading, the
    components, the open incidents and the maintenance windows.
    """

    provider = StatusPageProvider.STATUS_IO
    TIMEOUT = 10

    API = "https://api.status.io/1.0/status/{page_id}"

    # The page embeds its own id. The API cannot be reached without it,
    # and no URL tells a status.io page from any other.
    PAGE_ID = re.compile(
        r"statuspage_id[\"']?\s*[:=]\s*[\"']([0-9a-f]{16,})", re.IGNORECASE
    )

    # status.io's own scale. Anything unlisted is UNKNOWN rather than a
    # guess at green.
    SEVERITY = {
        100: Severity.OPERATIONAL,
        200: Severity.MAINTENANCE,
        300: Severity.DEGRADED,
        400: Severity.PARTIAL_OUTAGE,
        500: Severity.MAJOR_OUTAGE,
        600: Severity.MAJOR_OUTAGE,
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        # Nothing in a status.io URL says so. `identify` finds it by
        # asking the page, which is the only way.
        return False

    def _payload(self):
        if not hasattr(self, "_cached"):
            markup = self.get().text
            found = self.PAGE_ID.search(markup)
            if not found:
                raise ValueError(f"{self.url} is not a status.io page")
            response = self.http.get(
                self.API.format(page_id=found.group(1)), timeout=self.TIMEOUT
            )
            response.raise_for_status()
            self._cached = response.json()["result"]
        return self._cached

    def _severity(self, raw):
        return self.SEVERITY.get(int(raw or 0), Severity.UNKNOWN)

    def fetch_status(self):
        payload = self._payload()
        overall = payload.get("status_overall") or {}
        components = [
            NormalisedComponent(
                external_id="overall",
                name="Overall status",
                severity=self._severity(overall.get("status_code")),
                is_overall=True,
                order=-1,
            )
        ]
        for index, raw in enumerate(payload.get("status") or []):
            components.append(
                NormalisedComponent(
                    external_id=str(raw["id"]),
                    name=raw.get("name", ""),
                    severity=self._severity(raw.get("status_code")),
                    order=index,
                )
            )
        return components

    def _event(self, raw, kind, phase):
        return NormalisedEvent(
            external_id=str(raw.get("_id") or raw.get("id") or raw.get("name", "")),
            kind=kind,
            title=raw.get("name", ""),
            phase=phase,
            starts_at=timestamp(
                raw.get("datetime_open") or raw.get("datetime_planned_start")
            ),
            ends_at=timestamp(
                raw.get("datetime_closed") or raw.get("datetime_planned_end")
            ),
        )

    def fetch_incidents(self):
        payload = self._payload()
        events = [
            self._event(
                raw,
                EventKind.INCIDENT,
                IncidentPhase.RESOLVED
                if raw.get("datetime_closed")
                else IncidentPhase.INVESTIGATING,
            )
            for raw in payload.get("incidents") or []
        ]
        # Maintenance arrives split by whether it has started.
        maintenance = payload.get("maintenance") or {}
        for key, phase in (
            ("active", MaintenancePhase.IN_PROGRESS),
            ("upcoming", MaintenancePhase.SCHEDULED),
        ):
            events += [
                self._event(raw, EventKind.MAINTENANCE, phase)
                for raw in maintenance.get(key) or []
            ]
        return events

    def fetch_service_metadata(self):
        # The API carries no page name, so the service keeps the one the
        # importer derived from its URL.
        return {}
