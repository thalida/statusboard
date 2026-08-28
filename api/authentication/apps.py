from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_system_account(sender, **kwargs):
    """Put the system account in every database, as migrate finishes.

    It signs the rows the importer and the signals create. Made only on
    first use, it was missing from a database until something happened
    to write one, so the admin showed an audit trail with an author
    nobody could look up.

    This is where Django puts its own content types and permissions, so
    a new worktree gets the account with its schema and no data
    migration has to carry it.
    """
    from authentication.models import SYSTEM_EMAIL, User

    # Updated rather than fetched, so an account made before a column
    # existed is brought up to date instead of left half set up.
    account, _ = User.objects.update_or_create(
        email=SYSTEM_EMAIL,
        defaults={"is_active": False, "is_bot": True},
    )
    # It made itself, which is circular but true, and it leaves the one
    # row the system wrote that nothing had signed.
    if account.created_by_id is None:
        account.created_by = account
        account.updated_by = account
        account.save(update_fields=["created_by", "updated_by"])


class AuthenticationConfig(AppConfig):
    name = "authentication"

    def ready(self):
        post_migrate.connect(create_system_account, sender=self)
