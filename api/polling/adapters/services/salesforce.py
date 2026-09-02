from catalog.choices import StatusPageProvider
from polling.adapters.base import (
    Adapter,
    NormalisedComponent,
    NormalisedEvent,
    timestamp,
)
from status.choices import EventKind, IncidentPhase, Severity


class SalesforceAdapter(Adapter):
    """Salesforce Trust, whose obvious list is the wrong one.

    The API offers nearly four thousand instances. That is every pod
    and sandbox a customer might sit on, and nobody reads them.

    The twenty-one products are the components. Each carries a live
    count of the incidents open against it.
    """

    provider = StatusPageProvider.SALESFORCE
    host_specific = True
    TIMEOUT = 20

    API = "https://api.status.salesforce.com/v1"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "status.salesforce.com" in url

    @property
    def base_url(self):
        """The API, not the page. Nothing is read from the page itself."""
        return f"{self.API}/"

    @staticmethod
    def _count(raw, key):
        try:
            return int(raw.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    def fetch_status(self):
        products = self.get_json("products")
        components = []
        worst = Severity.OPERATIONAL
        for index, raw in enumerate(products):
            incidents = self._count(raw, "incidentCount")
            maintenance = self._count(raw, "maintenanceCount")
            severity = (
                Severity.PARTIAL_OUTAGE
                if incidents
                else Severity.MAINTENANCE
                if maintenance
                else Severity.OPERATIONAL
            )
            worst = min(worst, severity)
            components.append(
                NormalisedComponent(
                    external_id=str(raw["key"]),
                    name=raw.get("name", ""),
                    severity=severity,
                    order=index,
                )
            )
        return [
            NormalisedComponent(
                external_id="overall",
                name="Overall status",
                severity=worst,
                is_overall=True,
                order=-1,
            ),
            *components,
        ]

    def fetch_incidents(self):
        events = []
        for raw in self.get_json("incidents"):
            resolved = str(raw.get("status", "")).lower() == "resolved"
            events.append(
                NormalisedEvent(
                    external_id=str(raw["id"]),
                    kind=EventKind.MAINTENANCE
                    if str(raw.get("type", "")).lower() == "maintenance"
                    else EventKind.INCIDENT,
                    title=str(raw.get("type") or "Incident"),
                    phase=IncidentPhase.RESOLVED
                    if resolved
                    else IncidentPhase.INVESTIGATING,
                    starts_at=timestamp(raw.get("createdAt")),
                    ends_at=timestamp(raw.get("updatedAt")) if resolved else None,
                    # serviceKeys are internal names like "coreService" and
                    # do not map onto the product keys above.
                )
            )
        return events

    def fetch_service_metadata(self):
        return {"name": "Salesforce", "homepage_url": "https://www.salesforce.com/"}
