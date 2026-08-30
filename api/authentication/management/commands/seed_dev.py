from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from catalog.models import Service
from dashboards.models import Dashboard, DashboardItem

# Three real status pages, one of each shape worth having locally: a big
# tree to navigate, a small one to read whole, and one whose components
# nest. All Statuspage, because that is the adapter most services use.
SERVICES = [
    "https://www.githubstatus.com",
    "https://status.twilio.com",
    "https://status.openai.com",
]
# What the board tracks. The rest of the catalog stays untracked, which
# is what makes "tracked" mean anything on the dashboard.
TRACKED = "https://www.githubstatus.com"


class Command(BaseCommand):
    """Fill an empty local database with something to look at.

    `seed_admin` makes the account. This makes the data: a catalog, a
    board, and one tracked service so the poller has work and the admin
    dashboard has numbers. Safe to re-run.

    It fetches the three status pages, so it needs the network. Local
    only, for the same reason `seed_admin` is: a deployment must never
    grow rows because a command ran.
    """

    help = "Import a few real status pages and track one, for local development."

    def handle(self, *args, **options):
        if settings.ENVIRONMENT != "local":
            raise CommandError(
                f"seed_dev is local-only; ENVIRONMENT is {settings.ENVIRONMENT!r}."
            )

        call_command("seed_admin")
        owner = get_user_model().objects.filter(is_superuser=True).first()
        if owner is None:
            raise CommandError("No admin to own a board. Run `just env` first.")

        tracked = None
        for url in SERVICES:
            service, created = Service.objects.import_from_url(url)
            self.stdout.write(
                f"{'imported' if created else 'already had'} {service.name} "
                f"({service.components.count()} components)"
            )
            if url == TRACKED:
                tracked = service

        board = owner.default_dashboard or Dashboard.objects.filter(owner=owner).first()
        if board is None:
            raise CommandError("The admin has no board.")

        # The rollup, not a leaf: it is the row a new user would add
        # first, and tracking it is what makes the service polled.
        overall = tracked.components.filter(is_overall=True).first()
        _, added = DashboardItem.objects.get_or_create(
            dashboard=board,
            component=overall,
            defaults={"created_by": owner, "updated_by": owner},
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'tracked' if added else 'already tracking'} {overall} on {board.name}"
            )
        )
