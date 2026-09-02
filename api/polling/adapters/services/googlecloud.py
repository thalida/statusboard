from catalog.choices import StatusPageProvider
from polling.adapters.base import (
    Adapter,
    NormalisedComponent,
    NormalisedEvent,
    timestamp,
)
from status.choices import EventKind, IncidentPhase, Severity, StatusSource


class GoogleCloudAdapter(Adapter):
    """Google Cloud, which publishes products and incidents and no status.

    products.json lists every product and says nothing about how any of
    them is doing. incidents.json names the products each incident
    affects. So a product's state is read from the incidents open against
    it, which is what StatusSource.INCIDENTS records.
    """

    provider = StatusPageProvider.GOOGLE_CLOUD
    host_specific = True
    status_source = StatusSource.INCIDENTS

    # Google's own impact vocabulary.
    SEVERITY = {
        "SERVICE_OUTAGE": Severity.MAJOR_OUTAGE,
        "SERVICE_DISRUPTION": Severity.PARTIAL_OUTAGE,
        "SERVICE_INFORMATION": Severity.DEGRADED,
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "status.cloud.google.com" in url

    def _open_incidents(self):
        # No end time means it is still running.
        return [raw for raw in self.get_json("incidents.json") if not raw.get("end")]

    def fetch_status(self):
        worst = {}
        for raw in self._open_incidents():
            severity = self.SEVERITY.get(raw.get("status_impact"), Severity.DEGRADED)
            for product in raw.get("affected_products") or []:
                product_id = str(product.get("id"))
                # Lower is worse, so the smallest wins.
                worst[product_id] = min(
                    worst.get(product_id, Severity.OPERATIONAL), severity
                )

        components = [
            NormalisedComponent(
                external_id="overall",
                name="Overall status",
                severity=min(worst.values()) if worst else Severity.OPERATIONAL,
                is_overall=True,
                order=-1,
            )
        ]
        for index, product in enumerate(
            self.get_json("products.json").get("products", [])
        ):
            product_id = str(product.get("id"))
            components.append(
                NormalisedComponent(
                    external_id=product_id,
                    name=product.get("title", ""),
                    severity=worst.get(product_id, Severity.OPERATIONAL),
                    order=index,
                )
            )
        return components

    def fetch_incidents(self):
        events = []
        for raw in self.get_json("incidents.json"):
            closed = bool(raw.get("end"))
            events.append(
                NormalisedEvent(
                    external_id=str(raw["id"]),
                    kind=EventKind.INCIDENT,
                    title=raw.get("external_desc", ""),
                    phase=IncidentPhase.RESOLVED
                    if closed
                    else IncidentPhase.INVESTIGATING,
                    starts_at=timestamp(raw.get("begin")),
                    ends_at=timestamp(raw.get("end")),
                    affected_external_ids=tuple(
                        str(p["id"])
                        for p in raw.get("affected_products") or []
                        if p.get("id")
                    ),
                )
            )
        return events

    def fetch_service_metadata(self):
        return {"name": "Google Cloud", "homepage_url": "https://cloud.google.com/"}
