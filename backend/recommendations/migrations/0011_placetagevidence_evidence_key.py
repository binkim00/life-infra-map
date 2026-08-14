import uuid

import recommendations.models
from django.db import migrations, models


def populate_evidence_keys(apps, schema_editor):
    PlaceTagEvidence = apps.get_model("recommendations", "PlaceTagEvidence")
    for evidence in PlaceTagEvidence.objects.filter(evidence_key__isnull=True).iterator():
        evidence.evidence_key = uuid.uuid4().hex
        evidence.save(update_fields=["evidence_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("recommendations", "0010_datasourcesyncrun_placecoverage_placetagevidence_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="placetagevidence",
            name="evidence_key",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.RunPython(populate_evidence_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="placetagevidence",
            name="evidence_key",
            field=models.CharField(
                default=recommendations.models.new_evidence_key,
                editable=False,
                max_length=64,
                unique=True,
            ),
        ),
    ]
