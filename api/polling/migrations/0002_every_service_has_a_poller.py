from django.db import migrations

SYSTEM_EMAIL = "system@statusboard.invalid"


def make_missing_pollers(apps, schema_editor):
    """A service with no poller is never checked, and says nothing.

    The row was made by a signal, so anything that wrote a Service
    without sending one left a service nothing polls. `Service.save`
    makes it now. This is for the rows that predate that.
    """
    Service = apps.get_model("catalog", "Service")
    Poller = apps.get_model("polling", "Poller")
    User = apps.get_model("authentication", "User")

    author = User.objects.filter(email=SYSTEM_EMAIL).first()
    Poller.objects.bulk_create(
        Poller(service=service, created_by=author, updated_by=author)
        for service in Service.objects.filter(poller__isnull=True)
    )


class Migration(migrations.Migration):
    dependencies = [
        ("polling", "0001_initial"),
        ("authentication", "0003_system_account"),
    ]

    operations = [migrations.RunPython(make_missing_pollers, migrations.RunPython.noop)]
