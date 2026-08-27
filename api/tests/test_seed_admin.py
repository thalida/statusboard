import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from authentication.models import User


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "dev-only-password")


@pytest.fixture
def no_credentials(monkeypatch):
    monkeypatch.delenv("DJANGO_SUPERUSER_EMAIL", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)


@pytest.mark.django_db
def test_it_creates_an_admin_that_can_sign_in(credentials):
    from django.contrib.auth import authenticate

    call_command("seed_admin")
    assert authenticate(username="admin@example.com", password="dev-only-password")


@pytest.mark.django_db
def test_running_it_twice_does_not_create_a_second_admin(credentials):
    # `just init` calls it every run, including on a set-up worktree.
    call_command("seed_admin")
    call_command("seed_admin")
    assert User.objects.filter(is_superuser=True).count() == 1


@pytest.mark.django_db
def test_it_does_nothing_without_credentials(no_credentials):
    # It must never ask. `just env` owns the one prompt, so an answer
    # typed here would be lost and the next run would ask again.
    call_command("seed_admin")
    assert not User.objects.exists()


@pytest.mark.django_db
def test_it_refuses_to_run_outside_local(credentials, settings):
    # The guard that keeps a seeded admin out of a deployed database.
    settings.ENVIRONMENT = "production"
    with pytest.raises(CommandError):
        call_command("seed_admin")
    assert not User.objects.exists()
