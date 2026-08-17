from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recommendations", "0019_place_feature_document")]

    operations = [
        migrations.CreateModel(
            name="OperationsDashboardSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot_date", models.DateField(unique=True)),
                ("payload", models.JSONField(default=dict)),
                ("generated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [models.Index(fields=["-snapshot_date"], name="recommendati_snapsho_3e8bbd_idx")],
            },
        ),
    ]
