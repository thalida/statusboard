import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from api.defaults import Environment


class Command(BaseCommand):
    """Create the development admin, idempotently.

    This writes the database row. `just env` writes the .env.local that
    supplies the credentials. Each worktree has its own database, so this
    runs per worktree even though the .env.local is shared.

    It never asks. One prompt, in one place, or the answer goes somewhere
    the next run cannot find.

    Not a data migration. Migrations run everywhere the app is deployed.
    A superuser created in one is a known account in production. Its
    password would sit in git. This runs in development only.
    """

    help = "Create the development admin from DJANGO_SUPERUSER_EMAIL and _PASSWORD."

    def handle(self, *args, **options):
        if settings.ENVIRONMENT is not Environment.DEVELOPMENT:
            raise CommandError(
                f"seed_admin runs in development only; ENVIRONMENT is "
                f"{settings.ENVIRONMENT!r}."
            )

        user_model = get_user_model()
        existing = user_model.objects.filter(is_superuser=True).first()
        if existing is not None:
            self.stdout.write(f"admin already exists ({existing.email}).")
            return

        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not email or not password:
            self.stdout.write(
                "No admin, and .env.local has no credentials. Run `just env` to "
                "set them, then `just seed`."
            )
            return

        # A command made this one, so it is signed by the system rather
        # than left blank. Somebody who signs themselves up is not.
        system = user_model.objects.system()
        user_model.objects.create_superuser(
            email, password=password, created_by=system, updated_by=system
        )
        self.stdout.write(self.style.SUCCESS(f"created admin {email}"))
