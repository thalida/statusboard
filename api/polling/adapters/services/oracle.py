from urllib.parse import urljoin

import requests

from catalog.choices import StatusPageProvider
from polling.adapters.base import Adapter, NormalisedComponent
from status.choices import Severity


class OracleAdapter(Adapter):
    """Oracle Cloud, which serves half of Statuspage's API and its own half.

    status.json is Statuspage-shaped and carries the page-level
    reading. components.json is not. It is ninety regions, each with its
    own service health.

    The regions are the components. A service-by-region matrix would be
    thousands of rows nobody reads.
    """

    provider = StatusPageProvider.ORACLE
    host_specific = True

    INDICATOR = {
        "none": Severity.OPERATIONAL,
        "maintenance": Severity.MAINTENANCE,
        "minor": Severity.DEGRADED,
        "major": Severity.PARTIAL_OUTAGE,
        "critical": Severity.MAJOR_OUTAGE,
    }

    @classmethod
    def matches(cls, url: str) -> bool:
        return "ocistatus.oraclecloud.com" in url

    def _get(self, path):
        base = self.url if self.url.endswith("/") else self.url + "/"
        response = (self.session or requests).get(urljoin(base, path), timeout=15)
        response.raise_for_status()
        return response.json()

    def fetch_status(self):
        status = self._get("api/v2/status.json").get("status") or {}
        components = [
            NormalisedComponent(
                external_id="overall",
                name="Overall status",
                severity=self.INDICATOR.get(status.get("indicator"), Severity.UNKNOWN),
                is_overall=True,
                order=-1,
            )
        ]
        regions = self._get("api/v2/components.json").get("regionHealthReports") or []
        for index, region in enumerate(regions):
            unhealthy = [
                report
                for report in region.get("serviceHealthReports") or []
                if str(report.get("serviceHealth", "")).upper() not in ("", "HEALTHY")
            ]
            components.append(
                NormalisedComponent(
                    external_id=str(region["regionId"]),
                    name=region.get("regionName", ""),
                    severity=Severity.DEGRADED if unhealthy else Severity.OPERATIONAL,
                    order=index,
                )
            )
        return components

    def fetch_incidents(self):
        # Oracle publishes no incident list on these endpoints. An empty
        # list is honest; the component severities carry the state.
        return []

    def fetch_service_metadata(self):
        return {
            "name": "Oracle Cloud Infrastructure",
            "homepage_url": "https://www.oracle.com/cloud/",
        }
