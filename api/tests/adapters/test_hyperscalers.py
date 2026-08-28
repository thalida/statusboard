"""The pages that publish nothing standard: Apple, Oracle, Azure, Google."""

import json
from pathlib import Path

import pytest

from polling.adapters.services.apple import AppleAdapter
from polling.adapters.services.aws import AwsAdapter
from polling.adapters.services.azure import AzureAdapter
from polling.adapters.services.googlefeed import GoogleFeedAdapter
from polling.adapters.services.oracle import OracleAdapter
from status.choices import Severity

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class StubJson:
    """Serves a recorded payload per URL suffix. No network."""

    def __init__(self, bodies):
        self.bodies = bodies

    def get(self, url, **kwargs):
        for suffix, name in self.bodies.items():
            if url.endswith(suffix):
                body = json.loads((FIXTURES / name).read_text())
                return type(
                    "R",
                    (),
                    {
                        "json": lambda self, b=body: b,
                        "raise_for_status": lambda self: None,
                        "status_code": 200,
                    },
                )()
        raise AssertionError(f"unexpected url {url}")


@pytest.fixture
def apple():
    return AppleAdapter(
        "https://www.apple.com/support/systemstatus/",
        session=StubJson({"system_status_en_US.js": "apple_status.json"}),
    )


@pytest.fixture
def oracle():
    return OracleAdapter(
        "https://ocistatus.oraclecloud.com/",
        session=StubJson(
            {
                "status.json": "oracle_status.json",
                "components.json": "oracle_components.json",
            }
        ),
    )


def test_apple_returns_one_overall_component(apple):
    assert len([c for c in apple.fetch_status() if c.is_overall]) == 1


def test_apple_reads_a_service_as_healthy_when_it_has_no_events(apple):
    # A service carries no state of its own. Having nothing wrong is what
    # healthy means here.
    quiet = [c for c in apple.fetch_status() if not c.is_overall]
    assert quiet
    assert all(c.severity in {s.value for s in Severity} for c in quiet)


def test_apple_declares_it_reads_state_from_incidents(apple):
    from status.choices import StatusSource

    assert apple.status_source == StatusSource.INCIDENTS


def test_oracle_uses_the_pages_own_indicator_for_the_overall(oracle):
    # Never the worst region: one bad region would hold the whole cloud
    # orange forever.
    assert oracle.fetch_status()[0].severity in {s.value for s in Severity}


def test_oracle_lists_regions_not_a_service_by_region_matrix(oracle):
    components = [c for c in oracle.fetch_status() if not c.is_overall]
    assert len(components) > 20
    assert len(components) == len({c.external_id for c in components})


def test_oracle_reports_no_incidents_rather_than_inventing_them(oracle):
    # These endpoints carry no incident list. An empty list is honest.
    assert oracle.fetch_incidents() == []


@pytest.mark.parametrize(
    ("adapter_class", "mine", "theirs"),
    [
        (
            AwsAdapter,
            "https://health.aws.amazon.com/health/status",
            "https://status.acme.com/",
        ),
        (AzureAdapter, "https://azure.status.microsoft/", "https://status.acme.com/"),
        (
            GoogleFeedAdapter,
            "https://status.firebase.google.com/",
            "https://status.acme.com/",
        ),
        (
            AppleAdapter,
            "https://www.apple.com/support/systemstatus/",
            "https://status.acme.com/",
        ),
        (
            OracleAdapter,
            "https://ocistatus.oraclecloud.com/",
            "https://status.acme.com/",
        ),
    ],
)
def test_each_adapter_claims_only_its_own_page(adapter_class, mine, theirs):
    # Probing tries every adapter against every page. One that answered
    # for someone else's page would report its provider's events under
    # that service's name.
    assert adapter_class.matches(mine) is True
    assert adapter_class.matches(theirs) is False
