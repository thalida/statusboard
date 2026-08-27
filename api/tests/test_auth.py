from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import MagicLinkToken, User


@pytest.mark.django_db
def test_user_has_no_usable_password():
    # There is no password flow. A user with no password cannot be phished for one.
    user = User.objects.create(email="a@b.com")
    assert user.has_usable_password() is False
    assert User.USERNAME_FIELD == "email"


@pytest.mark.django_db
def test_requesting_a_link_sends_one_and_creates_a_token():
    response = APIClient().post(
        reverse("magic-link"), {"email": "a@b.com"}, format="json"
    )
    assert response.status_code == 204
    assert len(mail.outbox) == 1
    assert MagicLinkToken.objects.filter(user__email="a@b.com").count() == 1


@pytest.mark.django_db
def test_requesting_a_link_for_an_unknown_email_looks_identical():
    # The response must not reveal whether an account exists.
    first = APIClient().post(
        reverse("magic-link"), {"email": "new@b.com"}, format="json"
    )
    second = APIClient().post(
        reverse("magic-link"), {"email": "new@b.com"}, format="json"
    )
    assert first.status_code == second.status_code == 204


@pytest.mark.django_db
def test_verifying_returns_a_token_pair_and_stamps_last_login():
    APIClient().post(reverse("magic-link"), {"email": "a@b.com"}, format="json")
    token = MagicLinkToken.objects.get().token
    response = APIClient().post(reverse("verify"), {"token": token}, format="json")
    assert response.status_code == 200
    assert set(response.json()) == {"access", "refresh"}
    user = User.objects.get(email="a@b.com")
    assert user.last_login is not None


@pytest.mark.django_db
def test_a_token_cannot_be_used_twice():
    APIClient().post(reverse("magic-link"), {"email": "a@b.com"}, format="json")
    token = MagicLinkToken.objects.get().token
    APIClient().post(reverse("verify"), {"token": token}, format="json")
    again = APIClient().post(reverse("verify"), {"token": token}, format="json")
    assert again.status_code == 400


@pytest.mark.django_db
def test_an_expired_token_is_refused():
    APIClient().post(reverse("magic-link"), {"email": "a@b.com"}, format="json")
    link = MagicLinkToken.objects.get()
    link.expires_at = timezone.now() - timedelta(seconds=1)
    link.save(update_fields=["expires_at"])
    response = APIClient().post(reverse("verify"), {"token": link.token}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_me_requires_authentication():
    assert APIClient().get(reverse("me")).status_code == 401


@pytest.mark.django_db
def test_me_returns_the_signed_in_user():
    APIClient().post(reverse("magic-link"), {"email": "a@b.com"}, format="json")
    token = MagicLinkToken.objects.get().token
    pair = APIClient().post(reverse("verify"), {"token": token}, format="json").json()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair['access']}")
    body = client.get(reverse("me")).json()
    assert body["email"] == "a@b.com"
    assert set(body) == {"id", "email", "default_dashboard_id"}
    assert body["default_dashboard_id"] is not None


@pytest.mark.django_db
def test_deleting_the_account_removes_the_user():
    APIClient().post(reverse("magic-link"), {"email": "a@b.com"}, format="json")
    token = MagicLinkToken.objects.get().token
    pair = APIClient().post(reverse("verify"), {"token": token}, format="json").json()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair['access']}")
    assert client.delete(reverse("me")).status_code == 204
    assert User.objects.filter(email="a@b.com").exists() is False


@pytest.mark.django_db
def test_a_superuser_given_a_password_can_sign_in_to_the_admin():
    # Ordinary users stay passwordless. An admin cannot. The admin login
    # form authenticates by password. A superuser without one is locked
    # out of the site it administers.
    from django.contrib.auth import authenticate

    User.objects.create_superuser("admin@example.com", password="s3cret-for-a-test")
    user = authenticate(username="admin@example.com", password="s3cret-for-a-test")
    assert user is not None
    assert user.is_staff and user.is_superuser


@pytest.mark.django_db
def test_a_superuser_created_without_a_password_stays_locked_out():
    # Not a bug to fix by guessing a password — it is the honest outcome
    # of `createsuperuser --noinput` with no DJANGO_SUPERUSER_PASSWORD.
    User.objects.create_superuser("noauth@example.com")
    assert User.objects.get(email="noauth@example.com").has_usable_password() is False
