import pytest
from django.urls import reverse

from catalog.models import ServiceRequest
from tests.conftest import jwt_client

pytestmark = pytest.mark.django_db


def test_asking_records_the_url(client):
    # The write itself. Regressing here loses the row, and the admin
    # list this endpoint feeds has nothing to show.
    response = client.post(
        reverse("catalog-request"),
        {"url": "https://status.fastmail.com/"},
        content_type="application/json",
    )
    assert response.status_code == 202
    row = ServiceRequest.objects.get()
    assert row.url == "https://status.fastmail.com"
    assert row.request_count == 1
    # Anonymous stays anonymous. A future edit that stopped guarding
    # `is_authenticated` would only fail here, not on save.
    assert row.created_by is None


def test_asking_twice_counts_rather_than_duplicates(client):
    # State belongs to the URL, not to a request. A row per request
    # would answer one question twice once a URL was triaged.
    for _ in range(2):
        client.post(
            reverse("catalog-request"),
            {"url": "https://status.fastmail.com/"},
            content_type="application/json",
        )
    assert ServiceRequest.objects.count() == 1
    assert ServiceRequest.objects.get().request_count == 2


def test_two_spellings_of_one_url_are_one_row(client):
    # `url` is unique on the normalised form. Skipping normalisation
    # before the lookup would let a trailing slash duplicate the row
    # `normalise_url` exists to prevent.
    client.post(
        reverse("catalog-request"),
        {"url": "https://status.example.com/"},
        content_type="application/json",
    )
    client.post(
        reverse("catalog-request"),
        {"url": "https://status.example.com"},
        content_type="application/json",
    )
    assert ServiceRequest.objects.count() == 1
    assert ServiceRequest.objects.get().request_count == 2


def test_the_answer_is_the_same_whether_we_hold_it_or_not(client):
    # Always 202. A different code would reveal which URLs are
    # already in the catalog to anyone who asked.
    first = client.post(
        reverse("catalog-request"),
        {"url": "https://status.one.example/"},
        content_type="application/json",
    )
    second = client.post(
        reverse("catalog-request"),
        {"url": "https://status.one.example/"},
        content_type="application/json",
    )
    assert first.status_code == second.status_code == 202
    assert first.content == second.content


def test_a_signed_in_asker_is_recorded(user):
    # created_by carries it. There is no requested_by: that is what
    # BaseModel already holds. `force_login` leaves this view
    # answering 401, because there is no session backend.
    jwt_client(user).post(
        reverse("catalog-request"),
        {"url": "https://status.two.example/"},
        format="json",
    )
    assert ServiceRequest.objects.get().created_by == user


def test_a_malformed_url_is_refused(client):
    # Refused before it is stored. Skipping validation would let junk
    # into the row the admin list is ordered by.
    response = client.post(
        reverse("catalog-request"),
        {"url": "not a url"},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_a_failed_import_does_not_spend_this_endpoints_budget(client, monkeypatch):
    # Add-by-URL tries the import, then reports the same URL here. One
    # shared scope would let the import spend this endpoint's budget.
    # An asker who had already tried six times could never send us
    # the URL that failed.
    def refuses(url):
        raise ValueError(f"no adapter for {url}")

    monkeypatch.setattr("catalog.views.imports.import_from_url", refuses)
    for _ in range(6):
        client.post(
            reverse("catalog-import"),
            {"status_page_url": "https://status.example.com/"},
            content_type="application/json",
        )
    response = client.post(
        reverse("catalog-request"),
        {"url": "https://status.example.com/"},
        content_type="application/json",
    )
    assert response.status_code == 202
