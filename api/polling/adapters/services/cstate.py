import json

from catalog.choices import StatusPageProvider
from polling.adapters.base import Adapter, NormalisedComponent
from status.choices import Severity


class CStateAdapter(Adapter):
    """cState, the static status page generator behind Jenkins and others.

    One file describes the whole page: the systems, their state, and a
    summary. It is a general platform rather than one company's page, so
    it is found by probing like the rest.
    """

    provider = StatusPageProvider.CSTATE

    INDEX = "index.json"

    # cState's own vocabulary, taken from the colour keys it ships.
    SEVERITY = {
        "ok": Severity.OPERATIONAL,
        "notice": Severity.DEGRADED,
        "disrupted": Severity.PARTIAL_OUTAGE,
        "down": Severity.MAJOR_OUTAGE,
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        # Nothing in the URL says cState. Probing finds it.
        return False

    def _payload(self):
        if not hasattr(self, "_cached"):
            body = self.get(self.INDEX).text
            # cState writes descriptions straight from Markdown, so the
            # file can carry raw control characters that strict JSON
            # rejects.
            payload = json.loads(body, strict=False)
            if "cStateVersion" not in payload:
                raise ValueError(f"{self.url} is not a cState page")
            self._cached = payload
        return self._cached

    def _severity(self, value):
        return self.SEVERITY.get(str(value).lower(), Severity.UNKNOWN)

    def fetch_status(self):
        payload = self._payload()
        components = [
            NormalisedComponent(
                external_id="overall",
                name="Overall status",
                severity=self._severity(payload.get("summaryStatus")),
                is_overall=True,
                order=-1,
            )
        ]
        for index, system in enumerate(payload.get("systems") or []):
            components.append(
                NormalisedComponent(
                    external_id=system["name"],
                    name=system["name"],
                    severity=self._severity(system.get("status")),
                    order=index,
                )
            )
        return components

    def fetch_incidents(self):
        # index.json counts unresolved issues per system but does not
        # describe them. An empty list is honest; the severities carry
        # the state.
        return []

    def fetch_service_metadata(self):
        payload = self._payload()
        return {"name": payload.get("title", "")}
