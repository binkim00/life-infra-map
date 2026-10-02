from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("boards", "0010_inquiry_category")]

    operations = [
        migrations.RemoveConstraint(
            model_name="report",
            name="report_has_exactly_one_target",
        ),
        migrations.AddConstraint(
            model_name="report",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(post__isnull=False, comment__isnull=True)
                    | models.Q(post__isnull=True, comment__isnull=False)
                    | models.Q(status__in=["passed", "penalized"], post__isnull=True, comment__isnull=True)
                ),
                name="report_has_exactly_one_target",
            ),
        ),
    ]
