"""The three findings that turn a mistake into an incident."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories import ServiceFactory

INWARD = [
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://localhost:5432/",  # the database
    "http://127.0.0.1:8000/admin/",  # this service
    "http://[::1]/",
    "http://0.0.0.0/",
]


@pytest.mark.parametrize("url", INWARD)
def test_no_fetch_reaches_an_address_that_is_not_public(url):
    # `POST /catalog/import/` takes a URL from an unauthenticated body
    # and fetches it. Nothing inward is ours to read.
    from polling.fetch import BlockedAddress, check

    with pytest.raises(BlockedAddress):
        check(url)


@pytest.mark.parametrize("scheme", ["file:///etc/passwd", "gopher://x/", "ftp://x/"])
def test_only_http_is_fetched(scheme):
    from polling.fetch import BlockedAddress, check

    with pytest.raises(BlockedAddress):
        check(scheme)


def test_a_name_that_does_not_resolve_is_refused():
    # Fail closed. A name we cannot resolve is a name we do not fetch.
    from polling.fetch import BlockedAddress, check

    with pytest.raises(BlockedAddress):
        check("https://nothing.invalid/")


def test_the_guard_runs_on_the_way_out_not_only_on_the_way_in():
    # The check is in `send`, which a redirect goes through again. So a
    # page answering 302 to localhost is refused at the second hop too.
    import requests

    from polling.fetch import BlockedAddress, session

    prepared = requests.Request("GET", "http://127.0.0.1:8000/").prepare()

    with pytest.raises(BlockedAddress):
        session.send(prepared)


@pytest.mark.django_db
@pytest.mark.parametrize("url", INWARD)
def test_the_import_endpoint_refuses_an_inward_address(url):
    # A 400 with a reason, rather than a failure raised out of the probe.
    response = APIClient().post(
        reverse("catalog-import"), {"status_page_url": url}, format="json"
    )

    assert response.status_code == 400
    assert "status_page_url" in response.json()


@pytest.mark.django_db
def test_asking_for_sign_in_links_is_throttled():
    # Every call creates a user and mails an address nobody has proved
    # they own.
    client = APIClient()
    codes = [
        client.post(
            reverse("magic-link"), {"email": "flood@example.com"}, format="json"
        ).status_code
        for _ in range(8)
    ]

    assert 429 in codes


@pytest.mark.django_db
def test_one_inbox_cannot_be_buried_from_many_callers():
    # The scope counts per caller. This counts per recipient.
    codes = []
    for n in range(8):
        client = APIClient()
        codes.append(
            client.post(
                reverse("magic-link"),
                {"email": "target@example.com"},
                format="json",
                REMOTE_ADDR=f"203.0.113.{n}",
            ).status_code
        )

    assert 429 in codes


@pytest.mark.django_db
def test_importing_is_throttled():
    # Each call makes the server fetch a URL somebody else chose.
    client = APIClient()
    codes = [
        client.post(
            reverse("catalog-import"),
            {"status_page_url": "https://status.example.com/"},
            format="json",
        ).status_code
        for _ in range(10)
    ]

    assert 429 in codes


def test_reading_the_catalog_is_not_throttled_away(db):
    # The wide rates are the point: the catalog is public and scanned.
    ServiceFactory()
    client = APIClient()
    codes = [client.get(reverse("service-list")).status_code for _ in range(30)]

    assert set(codes) == {200}


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_a_deployment_will_not_run_on_the_key_in_this_repository(environment):
    from api.defaults import Environment, secret_key

    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
        secret_key(None, Environment(environment))
    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
        secret_key("   ", Environment(environment))


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_a_configured_key_is_used_everywhere(environment):
    from api.defaults import Environment, secret_key

    assert secret_key("a-real-key", Environment(environment)) == "a-real-key"


def test_development_may_run_on_the_repository_key():
    from api.defaults import DEV_SECRET_KEY, Environment, secret_key

    assert secret_key(None, Environment.DEVELOPMENT) == DEV_SECRET_KEY


@pytest.mark.parametrize(
    ("environment", "expected"),
    [("development", True), ("staging", False), ("production", False)],
)
def test_debug_follows_the_environment(environment, expected):
    # It used to default on, so a deployment that forgot the variable
    # served its tracebacks.
    from api.defaults import Environment, debug

    assert debug(None, Environment(environment)) is expected


@pytest.mark.parametrize("configured", ["1", "0"])
def test_debug_can_still_be_set_by_hand(configured):
    from api.defaults import Environment, debug

    assert debug(configured, Environment.PRODUCTION) is (configured == "1")
