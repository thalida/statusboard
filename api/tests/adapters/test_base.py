"""The parts every adapter shares."""

from datetime import datetime

import pytest
import requests

from catalog.choices import StatusPageProvider
from polling.adapters.base import Adapter, timestamp
from tests.adapters.conftest import StubSession


class Reader(Adapter):
    provider = StatusPageProvider.STATUSPAGE

    @classmethod
    def matches(cls, url):
        return False

    def fetch_status(self):
        return []

    def fetch_incidents(self):
        return []

    def fetch_service_metadata(self):
        return {}


@pytest.mark.parametrize("value", ["", None, "yesterday", "2026-13-45"])
def test_an_unusable_timestamp_reads_as_missing(value):
    # Six providers share this. One malformed date must not fail a poll.
    assert timestamp(value) is None


def test_a_written_timestamp_is_read():
    assert timestamp("2026-08-27T10:30:00+00:00") == datetime.fromisoformat(
        "2026-08-27T10:30:00+00:00"
    )


@pytest.mark.parametrize(
    ("url", "path", "asked"),
    [
        # A page under a path keeps it. Without the trailing slash
        # `urljoin` drops the last segment and asks the wrong host root.
        (
            "https://example.com/status",
            "api/v2/x.json",
            "https://example.com/status/api/v2/x.json",
        ),
        (
            "https://example.com/status/",
            "api/v2/x.json",
            "https://example.com/status/api/v2/x.json",
        ),
        ("https://example.com", "index.json", "https://example.com/index.json"),
        # No path means the page as given. A feed URL names a file.
        ("https://example.com/feed.xml", "", "https://example.com/feed.xml"),
    ],
)
def test_a_path_is_asked_for_under_the_page(url, path, asked):
    session = StubSession({asked: {"ok": True}})
    assert Reader(url, session=session).get_json(path) == {"ok": True}
    assert session.requested == [asked]


def test_a_failed_response_fails_the_poll():
    class Failing:
        def get(self, url, **kwargs):
            return type(
                "R",
                (),
                {
                    "raise_for_status": lambda self: (_ for _ in ()).throw(
                        requests.HTTPError("503")
                    )
                },
            )()

    with pytest.raises(requests.HTTPError):
        Reader("https://example.com", session=Failing()).get_json("index.json")
