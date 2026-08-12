"""
`backend/media/` 에 있던 업로드 파일을 현재 저장소(S3/MinIO)로 올립니다.

로컬 디렉터리에 두면 배포 시 컨테이너가 재시작될 때마다 파일이 사라지므로
저장소를 바꾸면서 기존 파일도 함께 옮깁니다.

원본 파일은 지우지 않습니다. 확인이 끝난 뒤 직접 지우세요.

사용
    python manage.py migrate_media_to_storage --dry-run
    python manage.py migrate_media_to_storage
"""

from pathlib import Path

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "backend/media/ 의 파일을 현재 기본 저장소로 업로드합니다."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="올리지 않고 목록만 보여줍니다.")

    def handle(self, *args, **options):
        if getattr(settings, "FILE_STORAGE_BACKEND", "local") != "s3":
            raise CommandError(
                "FILE_STORAGE_BACKEND 가 s3 가 아닙니다. 저장소를 바꾼 뒤 실행하세요."
            )

        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stdout.write("media 디렉터리가 없습니다. 옮길 파일이 없습니다.")
            return

        files = [path for path in media_root.rglob("*") if path.is_file()]
        if not files:
            self.stdout.write("옮길 파일이 없습니다.")
            return

        dry_run = options["dry_run"]
        total_bytes = sum(path.stat().st_size for path in files)
        self.stdout.write(f"대상 {len(files)}개, {total_bytes / 1024 / 1024:.1f}MB")

        uploaded = skipped = 0
        for path in files:
            # media_root 기준 상대 경로가 곧 저장소 키입니다. (예: profile_images/idle.png)
            key = path.relative_to(media_root).as_posix()

            if default_storage.exists(key):
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(f"  올릴 예정: {key}")
                uploaded += 1
                continue

            with path.open("rb") as handle:
                saved = default_storage.save(key, File(handle))
            if saved != key:
                # 이름이 바뀌었다면 같은 키가 이미 있다는 뜻이라 되돌립니다.
                default_storage.delete(saved)
                skipped += 1
                continue
            uploaded += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n{uploaded}개 올릴 예정, {skipped}개 이미 있음 (저장 안 함)"))
            return

        self.stdout.write(self.style.SUCCESS(f"\n{uploaded}개 업로드, {skipped}개 건너뜀"))
        self.stdout.write("원본은 그대로 두었습니다. 확인 후 backend/media/ 를 정리하세요.")
