from urllib.parse import urljoin

from catalog.choices import StatusPageProvider
from polling import fetch
from polling.adapters.base import Adapter, NormalisedComponent, NormalisedEvent
from status.choices import EventKind, IncidentPhase, Severity, StatusSource

DATA = "data/system_status_en_US.js"


class AppleAdapter(Adapter):
    """Apple's system status, which is a list of services and their events.

    A service carries no state of its own. It is healthy when it has no
    events, which is what StatusSource.INCIDENTS records.
    """

    provider = StatusPageProvider.APPLE
    host_specific = True
    status_source = StatusSource.INCIDENTS

    @classmethod
    def matches(cls, url: str) -> bool:
        return "apple.com/support/systemstatus" in url

    def _payload(self):
        if not hasattr(self, "_cached"):
            base = self.url if self.url.endswith("/") else self.url + "/"
            response = (self.session or fetch.session).get(
                urljoin(base, DATA), timeout=15
            )
            response.raise_for_status()
            self._cached = response.json()
        return self._cached

    def _services(self):
        return self._payload().get("services") or []

    def fetch_status(self):
        services = self._services()
        troubled = any(service.get("events") for service in services)
        components = [
            NormalisedComponent(
                external_id="overall",
                name="Overall status",
                severity=Severity.DEGRADED if troubled else Severity.OPERATIONAL,
                is_overall=True,
                order=-1,
            )
        ]
        for index, service in enumerate(services):
            components.append(
                NormalisedComponent(
                    external_id=service["serviceName"],
                    name=service["serviceName"],
                    severity=Severity.DEGRADED
                    if service.get("events")
                    else Severity.OPERATIONAL,
                    order=index,
                )
            )
        return components

    def fetch_incidents(self):
        events = []
        for service in self._services():
            for raw in service.get("events") or []:
                events.append(
                    NormalisedEvent(
                        external_id=f"{service['serviceName']}:{raw.get('epochStartDate')}",
                        kind=EventKind.INCIDENT,
                        title=raw.get("message") or service["serviceName"],
                        phase=IncidentPhase.RESOLVED
                        if raw.get("epochEndDate")
                        else IncidentPhase.INVESTIGATING,
                        starts_at=None,
                        affected_external_ids=(service["serviceName"],),
                    )
                )
        return events

    def fetch_service_metadata(self):
        return {"name": "Apple", "homepage_url": "https://www.apple.com/"}
