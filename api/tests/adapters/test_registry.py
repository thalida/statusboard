from dataclasses import FrozenInstanceError

import pytest

from catalog.adapters.base import Adapter, NormalisedComponent
from catalog.adapters.registry import detect
from catalog.choices import StatusPageProvider


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://status.twilio.com/", StatusPageProvider.STATUSPAGE),
        ("https://www.githubstatus.com/", StatusPageProvider.STATUSPAGE),
        ("https://status.instatus.com/", StatusPageProvider.INSTATUS),
        ("https://statuspage.betterstack.com/", StatusPageProvider.BETTERSTACK),
        ("https://example.com/feed.xml", StatusPageProvider.RSS),
    ],
)
def test_detect_picks_the_provider_from_the_url(url, expected):
    assert detect(url).provider == expected


def test_anything_unrecognised_falls_back_to_rss():
    # RSS is the fallback, not an error. A feed is still data.
    assert detect("https://weird.example.org/status").provider == StatusPageProvider.RSS


def test_every_adapter_implements_the_same_interface():
    for method in (
        "fetch_status",
        "fetch_incidents",
        "fetch_service_metadata",
        "matches",
    ):
        assert hasattr(Adapter, method)


def test_normalised_component_is_immutable():
    component = NormalisedComponent(
        external_id="a",
        name="SMS",
        severity=5,
        parent_external_id=None,
        order=0,
        is_overall=False,
    )
    with pytest.raises(FrozenInstanceError):
        component.name = "changed"
