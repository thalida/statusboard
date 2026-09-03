from django.db import migrations

SYSTEM_EMAIL = "system@statusboard.invalid"


def create_system_account(apps, schema_editor):
    """Put the system account in every database.

    It signs the rows the importer and the signals create. Made only on
    first use, it was missing until something happened to write one, so
    the admin showed an audit trail with an author nobody could look up.

    The address is written out rather than imported. A migration runs
    against the code of its own day, and a constant that moves later
    would change what this one did.
    """
    User = apps.get_model("authentication", "User")
    account, _ = User.objects.update_or_create(
        email=SYSTEM_EMAIL,
        defaults={"is_active": False, "is_bot": True},
    )
    # It made itself, which is circular but true. Without it the one row
    # the system wrote is the one row nothing signed.
    if account.created_by_id is None:
        account.created_by = account
        account.updated_by = account
        account.save(update_fields=["created_by", "updated_by"])


def delete_system_account(apps, schema_editor):
    """Only when nothing points at it. Rows it signed keep their author."""
    User = apps.get_model("authentication", "User")
    User.objects.filter(email=SYSTEM_EMAIL, created_by__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("authentication", "0002_initial")]

    operations = [
        migrations.RunPython(create_system_account, delete_system_account),
    ]
