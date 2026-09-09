from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0025_researchaudit"),
    ]

    operations = [
        migrations.AddField(
            model_name="placereport",
            name="client_request_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddConstraint(
            model_name="placereport",
            constraint=models.UniqueConstraint(
                fields=("user", "client_request_id"),
                name="unique_user_place_report_request",
            ),
        ),
    ]
