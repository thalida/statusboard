import getpass
import os
import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Create the local development admin, idempotently.

    Not a data migration. Migrations run everywhere the app is deployed.
    A superuser created in one is a known account in production. Its
    password would sit in git. This runs only where ENVIRONMENT is local.

    Credentials come from DJANGO_SUPERUSER_EMAIL and _PASSWORD. Without
    them it asks, so a fresh worktree needs no setup first. It never asks
    when stdin is not a terminal, which keeps CI unattended.
    """

    help = "Create the local dev admin. Prompts when the env vars are unset."

    def handle(self, *args, **options):
        if settings.ENVIRONMENT != "local":
            raise CommandError(
                f"seed_admin is local-only; ENVIRONMENT is {settings.ENVIRONMENT!r}."
            )

        user_model = get_user_model()
        existing = user_model.objects.filter(is_superuser=True).first()
        if existing is not None:
            # Already seeded. Say so and ask nothing, so `just init` stays
            # quiet on a worktree that is already set up.
            self.stdout.write(f"admin already exists ({existing.email}).")
            return

        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not email or not password:
            if not sys.stdin.isatty():
                self.stdout.write(
                    "No admin, and no DJANGO_SUPERUSER_EMAIL / _PASSWORD to make "
                    "one. Run `just seed` in a terminal, or `just superuser`."
                )
                return
            self.stdout.write("No admin yet. Enter one, or press Enter to skip.")
            email = email or input("admin email: ").strip()
            password = password or getpass.getpass("admin password: ")

        if not email or not password:
            self.stdout.write("Skipped. Run `just seed` later.")
            return

        user_model.objects.create_superuser(email, password=password)
        self.stdout.write(self.style.SUCCESS(f"created admin {email}"))
