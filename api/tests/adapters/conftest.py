import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class StubSession:
    """Return a recorded body per URL suffix. No network."""

    def __init__(self, bodies):
        self.bodies = bodies
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        for suffix, body in self.bodies.items():
            if url.endswith(suffix):
                return type(
                    "R",
                    (),
                    {
                        "json": lambda self, b=body: b,
                        "status_code": 200,
                        "raise_for_status": lambda self: None,
                        "headers": {},
                    },
                )()
        raise AssertionError(f"unexpected url {url}")


@pytest.fixture
def load():
    def _load(name):
        return json.loads((FIXTURES / name).read_text())

    return _load
