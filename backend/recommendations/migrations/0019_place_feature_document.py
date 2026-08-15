from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("recommendations", "0018_web_evidence_source_policy")]

    operations = [
        migrations.CreateModel(
            name="PlaceFeatureDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document", models.TextField()),
                ("features", models.JSONField(blank=True, default=list)),
                ("fingerprint", models.CharField(db_index=True, max_length=64)),
                ("embedding_provider", models.CharField(blank=True, max_length=50)),
                ("embedding_model", models.CharField(blank=True, max_length=100)),
                ("embedding", models.JSONField(blank=True, default=list)),
                ("embedding_dimensions", models.PositiveIntegerField(default=0)),
                ("indexed_at", models.DateTimeField(blank=True, null=True)),
                ("generated_at", models.DateTimeField(auto_now=True)),
                ("place", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="feature_document", to="recommendations.place")),
            ],
        ),
    ]
