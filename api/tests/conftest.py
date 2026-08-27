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
