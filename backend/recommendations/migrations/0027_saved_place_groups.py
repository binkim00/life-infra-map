from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("recommendations", "0026_placereport_idempotency"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserSavedPlaceGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("memo", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_place_groups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "-updated_at"], name="saved_group_user_updated_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "name"),
                        name="unique_user_saved_place_group_name",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="usersavedplace",
            name="group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="saved_places",
                to="recommendations.usersavedplacegroup",
            ),
        ),
    ]
