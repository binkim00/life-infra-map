from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recommendations", "0027_saved_place_groups")]

    operations = [
        migrations.AlterField(
            model_name="evidencereview",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "확인 필요"),
                    ("approved", "검토 승인"),
                    ("approved_limited", "제한 승인"),
                    ("rejected", "반려"),
                    ("research", "재조사 필요"),
                ],
                db_index=True,
                default="pending",
                max_length=24,
            ),
        ),
    ]
