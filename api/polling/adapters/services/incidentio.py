from catalog.choices import StatusPageProvider
from polling.adapters.services.statuspage import StatuspageAdapter


class IncidentIoAdapter(StatuspageAdapter):
    """incident.io, which speaks Statuspage's API.

    summary.json, status.json, components.json and incidents.json all
    match. There is no scheduled-maintenances endpoint, which the parent
    already treats as "no maintenance to report".

    Only pages on an incident.io domain are named here. A page on a
    company's own domain is wire-identical to Statuspage, so the URL
    cannot tell them apart and it is recorded as statuspage. It still
    polls correctly, which is what matters.
    """

    provider = StatusPageProvider.INCIDENT_IO

    @classmethod
    def matches(cls, url: str) -> bool:
        return "incident.io" in url
