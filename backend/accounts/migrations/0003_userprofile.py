from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_profiles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")

    for user in User.objects.all():
        nickname = user.username[:50] or "user"

        if UserProfile.objects.filter(nickname=nickname).exists():
            prefix = nickname[:43]
            index = 1

            while UserProfile.objects.filter(nickname=f"{prefix}-{index}").exists():
                index += 1

            nickname = f"{prefix}-{index}"

        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "nickname": nickname,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_delete_emailverificationcode_delete_userprofile"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nickname", models.CharField(max_length=50, unique=True, verbose_name="닉네임")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="생성일")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정일")),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="사용자",
                    ),
                ),
            ],
            options={
                "verbose_name": "사용자 프로필",
                "verbose_name_plural": "사용자 프로필",
            },
        ),
        migrations.RunPython(create_profiles, migrations.RunPython.noop),
    ]
