"""Two pages that needed thinking about, not just parsing."""

import json
from pathlib import Path

import pytest

from polling.adapters.services.auth0 import Auth0Adapter
from polling.adapters.services.salesforce import SalesforceAdapter
from status.choices import Severity

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class StubSalesforce:
    def __init__(self, incidents=()):
        self.incidents = list(incidents)

    def get(self, url, **kwargs):
        body = (
            json.loads((FIXTURES / "salesforce_products.json").read_text())
            if url.endswith("products")
            else self.incidents
        )
        return type(
            "R",
            (),
            {"json": lambda self, b=body: b, "raise_for_status": lambda self: None},
        )()


def test_salesforce_lists_products_not_instances():
    """The API offers nearly four thousand instances.

    Those are pods and sandboxes a customer might sit on, not components
    anyone reads. The products are.
    """
    components = SalesforceAdapter(
        "https://status.salesforce.com/", session=StubSalesforce()
    ).fetch_status()
    assert 5 < len(components) < 60
    assert len([c for c in components if c.is_overall]) == 1


def test_salesforce_separates_maintenance_from_an_incident():
    """A product carries live counts of both, and they are not the same.

    The recorded payload has one product under maintenance and the rest
    quiet, which is exactly the distinction worth keeping.
    """
    components = SalesforceAdapter(
        "https://status.salesforce.com/", session=StubSalesforce()
    ).fetch_status()
    states = {c.severity for c in components}
    assert Severity.OPERATIONAL in states
    assert Severity.MAINTENANCE in states
    assert Severity.PARTIAL_OUTAGE not in states


def test_salesforce_carries_an_open_incident_into_the_overall():
    adapter = SalesforceAdapter(
        "https://status.salesforce.com/", session=StubSalesforce()
    )
    adapter.session.get = lambda url, **kw: type(
        "R",
        (),
        {
            "json": lambda self: (
                [{"key": "Sales", "name": "Sales", "incidentCount": "1"}]
                if url.endswith("products")
                else []
            ),
            "raise_for_status": lambda self: None,
        },
    )()
    components = adapter.fetch_status()
    assert components[0].severity == Severity.PARTIAL_OUTAGE


def test_auth0_says_what_it_needs_rather_than_failing_silently():
    """Auth0's feed is per tenant, so nothing can discover it.

    Only the person adding the service knows their tenant. Without this
    the page fails like any unreadable one and the reason never reaches
    them.
    """
    adapter = Auth0Adapter("https://status.auth0.com/")
    with pytest.raises(ValueError, match="per tenant"):
        adapter.fetch_status()


def test_auth0_reads_a_tenant_feed_like_any_other():
    from tests.adapters.test_rss import StubTextSession

    feed = (FIXTURES / "rss_feed.xml").read_text()
    adapter = Auth0Adapter(
        "https://status.auth0.com/rss?domain=acme.us.auth0.com",
        session=StubTextSession(feed),
    )
    assert adapter.fetch_status()


def test_auth0_only_claims_auth0():
    assert Auth0Adapter.matches("https://status.auth0.com/") is True
    assert Auth0Adapter.matches("https://status.acme.com/") is False
