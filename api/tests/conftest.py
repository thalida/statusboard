import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if any test reaches the internet.

    Postgres opens its socket once, in session-scoped test-db setup,
    before this per-test fixture runs, so the database is unaffected.
    """

    def blocked(*args, **kwargs):
        raise AssertionError(
            "A test tried to make a network call. Adapters are tested against "
            "recorded fixtures in tests/fixtures/."
        )

    monkeypatch.setattr("socket.socket.connect", blocked)


@pytest.fixture(autouse=True)
def app_url(settings):
    """The client this deployment serves, for tests that mail a link.

    There is no default in settings, because a guess would mail an
    address nothing serves. Anything asserting on the absence sets it
    back.
    """
    settings.APP_URL = "https://statusboard.app"


@pytest.fixture(autouse=True)
def forget_throttles():
    """Throttle counters live in the cache, which outlives a test.

    Without this, the fifth test to ask for a sign-in link is refused
    for something the fourth one did.
    """
    from django.core.cache import cache

    cache.clear()
