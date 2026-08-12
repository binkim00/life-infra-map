"""
기존 SQLite 데이터를 Postgres 로 옮깁니다.

`dumpdata`/`loaddata` 는 786,882건을 한 번에 JSON 으로 만들어 메모리를 크게 쓰므로,
모델별로 나눠 읽고 배치로 넣습니다.

전제
- `.env` 의 `DB_ENGINE=postgres`
- Postgres 쪽에 `manage.py migrate` 가 끝나 스키마가 있어야 합니다.
- SQLite 파일은 `LEGACY_SQLITE_PATH` (기본값 backend/db.sqlite3) 에서 읽습니다.

사용
    python manage.py migrate_sqlite_to_postgres --dry-run
    python manage.py migrate_sqlite_to_postgres
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction


LEGACY = "legacy_sqlite"

# 외래키가 가리키는 쪽을 먼저 넣어야 합니다.
COPY_ORDER = [
    ("contenttypes", "ContentType"),
    ("auth", "Permission"),
    ("auth", "Group"),
    ("auth", "User"),
    ("authtoken", "Token"),
    ("accounts", "UserProfile"),
    ("recommendations", "Tag"),
    ("recommendations", "Place"),
    ("recommendations", "PlaceTag"),
    ("recommendations", "UserSearchLog"),
    ("recommendations", "UserPreference"),
    ("recommendations", "UserSavedPlace"),
    ("recommendations", "PlaceReport"),
    ("recommendations", "PlaceReportImage"),
    ("boards", "Post"),
    ("boards", "Comment"),
    ("boards", "PostLike"),
    ("boards", "CommentLike"),
    ("boards", "CommentDislike"),
    ("boards", "Report"),
    ("boards", "Notification"),
    ("boards", "Inquiry"),
    ("boards", "UserPenalty"),
    ("admin", "LogEntry"),
]

BATCH_SIZE = 2000


class Command(BaseCommand):
    help = "SQLite 데이터를 현재 기본 DB(Postgres)로 복사합니다."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="건수만 비교하고 쓰지 않습니다.")
        parser.add_argument("--only", nargs="*", help="특정 모델만 복사합니다. 예: --only Place PlaceTag")

    def handle(self, *args, **options):
        if LEGACY not in connections:
            raise CommandError(
                f"`{LEGACY}` 연결이 없습니다. DB_ENGINE=postgres 로 두고 SQLite 파일 경로를 확인하세요."
            )
        if connections["default"].vendor == "sqlite":
            raise CommandError("기본 DB가 아직 SQLite 입니다. DB_ENGINE=postgres 로 바꾸고 다시 실행하세요.")

        only = {name.lower() for name in (options.get("only") or [])}
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run: 쓰지 않습니다.\n"))

        total_copied = 0
        for app_label, model_name in COPY_ORDER:
            if only and model_name.lower() not in only:
                continue
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                self.stdout.write(f"  {app_label}.{model_name:<18} 모델 없음, 건너뜀")
                continue

            source_count = model.objects.using(LEGACY).count()
            target_count = model.objects.using("default").count()
            label = f"{app_label}.{model_name}"

            if source_count == 0:
                self.stdout.write(f"  {label:<34} 원본 0건, 건너뜀")
                continue
            if target_count:
                self.stdout.write(
                    self.style.WARNING(f"  {label:<34} 대상에 이미 {target_count:,}건 있음, 건너뜀")
                )
                continue
            if dry_run:
                self.stdout.write(f"  {label:<34} {source_count:>9,}건 복사 예정")
                continue

            copied = self.copy_model(model)
            total_copied += copied
            self.stdout.write(self.style.SUCCESS(f"  {label:<34} {copied:>9,}건 복사"))

        if dry_run:
            return

        self.reset_sequences()
        self.stdout.write(self.style.SUCCESS(f"\n총 {total_copied:,}건 복사 완료"))

    def copy_model(self, model):
        """PK 를 그대로 유지한 채 배치로 복사합니다."""
        copied = 0
        batch = []
        # `iterator()` 로 SQLite 쪽을 스트리밍해 메모리를 아낍니다.
        for obj in model.objects.using(LEGACY).order_by("pk").iterator(chunk_size=BATCH_SIZE):
            obj._state.db = None
            batch.append(obj)
            if len(batch) >= BATCH_SIZE:
                copied += self.flush(model, batch)
                batch = []
        if batch:
            copied += self.flush(model, batch)
        return copied

    def flush(self, model, batch):
        with transaction.atomic(using="default"):
            model.objects.using("default").bulk_create(batch, batch_size=BATCH_SIZE)
        return len(batch)

    def reset_sequences(self):
        """
        PK 를 명시해서 넣었기 때문에 시퀀스가 1에 머물러 있습니다.
        이대로 두면 새 글을 쓸 때 중복 키 오류가 납니다.
        """
        self.stdout.write("\n시퀀스 재설정")
        connection = connections["default"]
        with connection.cursor() as cursor:
            for app_label, model_name in COPY_ORDER:
                try:
                    model = apps.get_model(app_label, model_name)
                except LookupError:
                    continue
                pk = model._meta.pk
                if not pk.get_internal_type().endswith("AutoField"):
                    continue
                table = model._meta.db_table
                cursor.execute(
                    """
                    SELECT setval(
                        pg_get_serial_sequence(%s, %s),
                        COALESCE((SELECT MAX(id) FROM "%s"), 1),
                        (SELECT MAX(id) IS NOT NULL FROM "%s")
                    )
                    """
                    % ("%s", "%s", table, table),
                    [table, pk.column],
                )
        self.stdout.write("  완료")
