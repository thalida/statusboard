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
    from authentication.models import User

    User.objects.system()


class AuthenticationConfig(AppConfig):
    name = "authentication"

    def ready(self):
        post_migrate.connect(create_system_account, sender=self)
