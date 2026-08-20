#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_BUCKET:?BACKUP_BUCKET must be set}"

AWS_REGION="${AWS_REGION:-ap-northeast-2}"
BACKUP_PREFIX="${BACKUP_PREFIX:-postgresql}"
DB_CONTAINER="${DB_CONTAINER:-life-infra-map-runtime-db}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_name="life_infra_map-${timestamp}.dump"
backup_file="$(mktemp "/var/tmp/${backup_name}.XXXXXX")"

cleanup() {
  rm -f -- "$backup_file"
}
trap cleanup EXIT

if [ "$(docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null || true)" != "true" ]; then
  echo "Database container is not running: ${DB_CONTAINER}" >&2
  exit 1
fi

docker exec "$DB_CONTAINER" sh -ceu '
  exec pg_dump \
    --format=custom \
    --compress=6 \
    --no-owner \
    --no-privileges \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB"
' > "$backup_file"

docker exec -i "$DB_CONTAINER" pg_restore --list < "$backup_file" > /dev/null

backup_size="$(stat -c '%s' "$backup_file")"
backup_sha256="$(sha256sum "$backup_file" | awk '{print $1}')"
backup_key="${BACKUP_PREFIX%/}/${backup_name}"

export AWS_REGION BACKUP_BUCKET backup_file backup_key backup_size backup_sha256
python3 - <<'PY'
import json
import os

import boto3


region = os.environ["AWS_REGION"]
bucket = os.environ["BACKUP_BUCKET"]
backup_file = os.environ["backup_file"]
key = os.environ["backup_key"]
expected_size = int(os.environ["backup_size"])
sha256 = os.environ["backup_sha256"]

s3 = boto3.client("s3", region_name=region)
s3.upload_file(
    backup_file,
    bucket,
    key,
    ExtraArgs={
        "ContentType": "application/octet-stream",
        "Metadata": {"sha256": sha256},
        "ServerSideEncryption": "AES256",
        "StorageClass": "STANDARD",
    },
)
uploaded = s3.head_object(Bucket=bucket, Key=key)
actual_size = int(uploaded["ContentLength"])
actual_sha256 = (uploaded.get("Metadata") or {}).get("sha256", "")
if actual_size != expected_size or actual_sha256 != sha256:
    raise RuntimeError(
        "Uploaded backup verification failed: "
        f"size={actual_size}/{expected_size}, sha256={actual_sha256}/{sha256}"
    )

print(
    json.dumps(
        {
            "status": "uploaded",
            "bucket": bucket,
            "key": key,
            "bytes": actual_size,
            "sha256": sha256,
        },
        sort_keys=True,
    )
)
PY
