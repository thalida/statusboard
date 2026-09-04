from django.db import migrations, models

# How a service reached the catalog. `created_by` says who added it, and
# this says how. Every existing row reads manual, which is true of one
# nobody imported.


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_drop_derived_ancestry_and_search"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalservice",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "Added by hand"),
                    ("import", "Imported from a status page"),
                ],
                db_default="manual",
                default="manual",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "Added by hand"),
                    ("import", "Imported from a status page"),
                ],
                db_default="manual",
                default="manual",
                max_length=32,
            ),
        ),
    ]
