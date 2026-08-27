import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Poller, Service, StatusPage


class FakeAdapter:
    provider = "statuspage"

    def __init__(self, url, session=None):
        self.url = url

    def fetch_status(self):
        from catalog.adapters.base import NormalisedComponent

        return [
            NormalisedComponent("overall", "Twilio", 5, is_overall=True),
            NormalisedComponent("a", "SMS", 5),
        ]

    def fetch_incidents(self):
        return []

    def fetch_service_metadata(self):
        return {"name": "Twilio", "homepage_url": "https://twilio.com"}


@pytest.fixture(autouse=True)
def fake_detect(monkeypatch):
    monkeypatch.setattr("catalog.import_service.detect", lambda url: FakeAdapter)


@pytest.mark.django_db
def test_importing_creates_the_service_its_status_page_and_its_poller():
    response = APIClient().post(
        reverse("catalog-import"), {"url": "https://status.twilio.com/"}, format="json"
    )
    assert response.status_code == 201
    service = Service.objects.get()
    assert StatusPage.objects.filter(service=service).exists()
    assert Poller.objects.filter(service=service).exists()


@pytest.mark.django_db
def test_the_same_url_resolves_to_the_same_service_and_returns_200():
    url = reverse("catalog-import")
    first = APIClient().post(url, {"url": "https://status.twilio.com/"}, format="json")
    second = APIClient().post(url, {"url": "https://status.twilio.com/"}, format="json")
    assert first.status_code == 201
    assert second.status_code == 200
    assert Service.objects.count() == 1


@pytest.mark.django_db
def test_urls_are_deduplicated_after_normalising():
    # One status page gives one service and one poll.
    url = reverse("catalog-import")
    APIClient().post(url, {"url": "https://status.twilio.com/"}, format="json")
    APIClient().post(url, {"url": "https://status.twilio.com"}, format="json")
    assert Service.objects.count() == 1


@pytest.mark.django_db
def test_the_imported_service_is_identical_in_shape_to_a_listed_one():
    # If a field is missing here it belongs in the list too, not in a second shape.
    created = (
        APIClient()
        .post(
            reverse("catalog-import"),
            {"url": "https://status.twilio.com/"},
            format="json",
        )
        .json()
    )
    listed = APIClient().get(reverse("service-list")).json()["results"][0]
    assert set(created) == set(listed)


@pytest.mark.django_db
def test_the_response_carries_the_detected_provider():
    body = (
        APIClient()
        .post(
            reverse("catalog-import"),
            {"url": "https://status.twilio.com/"},
            format="json",
        )
        .json()
    )
    assert body["status_page"]["provider"] == "statuspage"


@pytest.mark.django_db
def test_a_missing_url_is_a_400():
    assert (
        APIClient().post(reverse("catalog-import"), {}, format="json").status_code
        == 400
    )
