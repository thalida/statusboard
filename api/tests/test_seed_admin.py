import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from authentication.models import User


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "dev-only-password")


@pytest.mark.django_db
def test_it_creates_an_admin_that_can_sign_in(credentials):
    from django.contrib.auth import authenticate

    call_command("seed_admin")
    user = authenticate(username="admin@example.com", password="dev-only-password")
    assert user is not None


@pytest.mark.django_db
def test_running_it_twice_does_not_create_a_second_admin(credentials):
    # `just init` calls it every run, including on a set-up worktree.
    call_command("seed_admin")
    call_command("seed_admin")
    assert User.objects.filter(is_superuser=True).count() == 1


@pytest.mark.django_db
def test_it_never_prompts_when_an_admin_exists(monkeypatch):
    # The prompt must not block `just init` on an existing worktree.
    User.objects.create_superuser("first@example.com", password="x")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(
        "builtins.input", lambda *a: pytest.fail("asked for an email anyway")
    )
    call_command("seed_admin")
    assert User.objects.filter(is_superuser=True).count() == 1


@pytest.mark.django_db
def test_it_prompts_when_there_is_no_admin_and_no_credentials(monkeypatch):
    monkeypatch.delenv("DJANGO_SUPERUSER_EMAIL", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a: "typed@example.com")
    monkeypatch.setattr("getpass.getpass", lambda *a: "typed-password")
    call_command("seed_admin")
    assert User.objects.filter(email="typed@example.com").exists()


@pytest.mark.django_db
def test_an_empty_answer_skips_rather_than_creating_a_broken_admin(monkeypatch):
    monkeypatch.delenv("DJANGO_SUPERUSER_EMAIL", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    monkeypatch.setattr("getpass.getpass", lambda *a: "")
    call_command("seed_admin")
    assert not User.objects.exists()


@pytest.mark.django_db
def test_it_does_not_prompt_without_a_terminal(monkeypatch):
    # CI must not hang waiting for an answer.
    monkeypatch.delenv("DJANGO_SUPERUSER_EMAIL", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr(
        "builtins.input", lambda *a: pytest.fail("prompted with no terminal")
    )
    call_command("seed_admin")
    assert not User.objects.exists()


@pytest.mark.django_db
def test_it_refuses_to_run_outside_local(credentials, settings):
    # The guard that keeps a seeded admin out of a deployed database.
    settings.ENVIRONMENT = "production"
    with pytest.raises(CommandError):
        call_command("seed_admin")
    assert not User.objects.exists()
