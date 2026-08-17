from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recommendations", "0020_operations_dashboard_snapshot")]

    operations = [
        migrations.RenameIndex(
            model_name="operationsdashboardsnapshot",
            old_name="recommendati_snapsho_3e8bbd_idx",
            new_name="ops_snapshot_date_idx",
        ),
        migrations.AddIndex(
            model_name="placetag",
            index=models.Index(fields=["created_at"], name="pt_created_idx"),
        ),
        migrations.AddIndex(
            model_name="placetagevidence",
            index=models.Index(fields=["created_at"], name="pte_created_idx"),
        ),
    ]
