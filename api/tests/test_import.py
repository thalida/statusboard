import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Service, StatusPage
from polling.adapters.base import Adapter
from polling.importer import import_from_url
from polling.models import Poller


class FakeAdapter(Adapter):
    """A stand-in that has to satisfy the real interface.

    Not a bare class. One drifted from the base and kept passing, so a
    method every adapter inherits was missing here and nowhere else.
    """

    provider = "statuspage"

    @classmethod
    def matches(cls, url):
        return True

    def fetch_status(self):
        from polling.adapters.base import NormalisedComponent

        return [
            NormalisedComponent("overall", "Twilio", 5, is_overall=True),
            NormalisedComponent("a", "SMS", 5),
        ]

    def fetch_incidents(self):
        return []

    def fetch_service_metadata(self):
        return {"name": "Twilio", "homepage_url": "https://twilio.com"}

    def fetch_logo(self):
        return "https://cdn.example/logo.png"


@pytest.fixture(autouse=True)
def fake_detect(monkeypatch):
    monkeypatch.setattr(
        "polling.importer.identify",
        lambda url, session=None: (FakeAdapter, url),
    )


@pytest.mark.django_db
def test_importing_creates_the_service_its_status_page_and_its_poller():
    response = APIClient().post(
        reverse("catalog-import"),
        {"status_page_url": "https://status.twilio.com/"},
        format="json",
    )
    assert response.status_code == 201
    service = Service.objects.get()
    assert StatusPage.objects.filter(service=service).exists()
    assert Poller.objects.filter(service=service).exists()


@pytest.mark.django_db
def test_the_same_url_resolves_to_the_same_service_and_returns_200():
    url = reverse("catalog-import")
    first = APIClient().post(
        url, {"status_page_url": "https://status.twilio.com/"}, format="json"
    )
    second = APIClient().post(
        url, {"status_page_url": "https://status.twilio.com/"}, format="json"
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert Service.objects.count() == 1


@pytest.mark.django_db
def test_urls_are_deduplicated_after_normalising():
    # One status page gives one service and one poll.
    url = reverse("catalog-import")
    APIClient().post(
        url, {"status_page_url": "https://status.twilio.com/"}, format="json"
    )
    APIClient().post(
        url, {"status_page_url": "https://status.twilio.com"}, format="json"
    )
    assert Service.objects.count() == 1


@pytest.mark.django_db
def test_the_imported_service_is_identical_in_shape_to_a_read_one():
    # If a field is missing here it belongs on the service page too,
    # not in a second shape.
    created = (
        APIClient()
        .post(
            reverse("catalog-import"),
            {"status_page_url": "https://status.twilio.com/"},
            format="json",
        )
        .json()
    )
    url = reverse("service-detail", args=[created["slug"]])
    assert set(created) == set(APIClient().get(url).json())


@pytest.mark.django_db
def test_the_response_carries_the_detected_provider():
    body = (
        APIClient()
        .post(
            reverse("catalog-import"),
            {"status_page_url": "https://status.twilio.com/"},
            format="json",
        )
        .json()
    )
    assert body["status_page"]["provider"] == "statuspage"


@pytest.mark.django_db
def test_a_missing_status_page_url_is_a_400():
    response = APIClient().post(reverse("catalog-import"), {}, format="json")
    assert response.status_code == 400
    # The serializer's own field map, not the `Error` shape. The
    # contract documents both under this code, and a client tells them
    # apart by whether `code` is there.
    assert response.json() == {"status_page_url": ["This field is required."]}


def test_normalising_keeps_the_www_prefix():
    # It is the address a poll fetches, not only a key. githubstatus.com
    # redirects to the www root page, so a stripped host turns
    # "api/v2/summary.json" into the HTML homepage.
    from catalog.models import StatusPage

    assert (
        StatusPage.normalise_url("https://www.githubstatus.com/")
        == "https://www.githubstatus.com"
    )


def test_normalising_still_ignores_case_query_and_trailing_slash():
    from catalog.models import StatusPage

    assert (
        StatusPage.normalise_url("HTTPS://Status.Twilio.com/?utm=x#top")
        == "https://status.twilio.com"
    )


@pytest.mark.django_db
def test_a_provider_that_names_nothing_still_gets_a_service_name(monkeypatch):
    # Half the providers publish no name, and one that does publishes it
    # empty. A service has to be called something to be imported.
    class Nameless(Adapter):
        provider = "rss"

        @classmethod
        def matches(cls, url):
            return True

        def fetch_status(self):
            return []

        def fetch_incidents(self):
            return []

        def fetch_service_metadata(self):
            return {"name": ""}

        def fetch_logo(self):
            return ""

    monkeypatch.setattr(
        "polling.importer.identify",
        lambda url: (Nameless, url),
    )
    service, created = import_from_url("https://status.nameless.test/")

    assert created
    assert service.name == "status.nameless.test"


@pytest.mark.django_db
def test_a_poll_keeps_the_old_name_when_a_provider_stops_publishing_one():
    # `named_metadata` is the importer's. A poll must not overwrite a
    # real name with a host every time the provider answers without one.
    from polling.tasks import _refresh_metadata
    from tests.factories import ServiceFactory

    service = ServiceFactory(name="Twilio")

    _refresh_metadata(service, {"name": ""})

    service.refresh_from_db()
    assert service.name == "Twilio"


@pytest.mark.django_db
def test_the_page_is_read_before_a_transaction_opens(monkeypatch):
    # A provider takes seconds to answer. A database connection must not
    # spend them waiting on one.
    #
    # The suite runs each test in a transaction, so depth is what can
    # be measured. The fetch must open none of its own.
    from django.db import connection

    depth = []

    class Watching(FakeAdapter):
        def fetch_status(self):
            depth.append(len(connection.savepoint_ids))
            return super().fetch_status()

    monkeypatch.setattr(
        "polling.importer.identify",
        lambda url, session=None: (Watching, url),
    )
    outer = len(connection.savepoint_ids)
    import_from_url("https://status.watched.test/")

    assert depth == [outer]


@pytest.mark.django_db
def test_a_second_import_of_the_same_page_returns_the_first_service():
    # The fetch is outside the transaction, so two callers can read the
    # same page at once. The second must not make a second service.
    first, created = import_from_url("https://status.race.test/")
    second, again = import_from_url("https://status.race.test/")

    assert created is True
    assert again is False
    assert second.pk == first.pk
    assert Service.objects.count() == 1


@pytest.mark.django_db
def test_an_import_records_the_caller_who_asked_for_it(user):
    # The bot signs automated rows only. Dropping the caller here
    # records a person's import as the system account.
    from tests.conftest import jwt_client

    jwt_client(user).post(
        reverse("catalog-import"),
        {"status_page_url": "https://status.twilio.com/"},
        format="json",
    )

    assert Service.objects.get().created_by == user


@pytest.mark.django_db
def test_an_anonymous_import_names_nobody_rather_than_the_bot():
    # The endpoint is AllowAny, so a signed-out person can import. A
    # service request answers this the same way, with null. A person
    # asked, and the system account would claim a job did.
    APIClient().post(
        reverse("catalog-import"),
        {"status_page_url": "https://status.twilio.com/"},
        format="json",
    )

    assert Service.objects.get().created_by is None
