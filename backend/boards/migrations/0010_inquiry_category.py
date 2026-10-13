from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("boards", "0009_add_report_received_notification_type")]

    operations = [
        migrations.AddField(
            model_name="inquiry",
            name="category",
            field=models.CharField(
                choices=[
                    ("general", "일반 문의"),
                    ("service_issue", "서비스 불편"),
                    ("bug", "오류 신고"),
                ],
                default="general",
                max_length=20,
                verbose_name="문의 유형",
            ),
        ),
    ]
