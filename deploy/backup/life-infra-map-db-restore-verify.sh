#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_BUCKET:?BACKUP_BUCKET must be set}"

AWS_REGION="${AWS_REGION:-ap-northeast-2}"
BACKUP_PREFIX="${BACKUP_PREFIX:-postgresql}"
POSTGIS_IMAGE="${RESTORE_VERIFY_POSTGIS_IMAGE:-postgis/postgis:16-3.4}"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
container_name="life-infra-map-restore-verify-${run_id}"
volume_name="life-infra-map-restore-verify-${run_id}-data"
work_dir="$(mktemp -d /var/tmp/life-infra-map-restore-verify.XXXXXX)"
backup_file="${work_dir}/latest.dump"
metadata_file="${work_dir}/metadata.json"

cleanup() {
  exit_code=$?
  if [ "$exit_code" -ne 0 ] && docker inspect "$container_name" >/dev/null 2>&1; then
    echo "Restore verification container logs:" >&2
    docker logs --tail 80 "$container_name" >&2 || true
  fi
  docker rm -f -- "$container_name" >/dev/null 2>&1 || true
  docker volume rm -- "$volume_name" >/dev/null 2>&1 || true
  rm -rf -- "$work_dir"
  return "$exit_code"
}
trap cleanup EXIT

export AWS_REGION BACKUP_BUCKET BACKUP_PREFIX backup_file metadata_file
python3 - <<'PY'
import hashlib
import json
import os

import boto3


s3 = boto3.client("s3", region_name=os.environ["AWS_REGION"])
bucket = os.environ["BACKUP_BUCKET"]
prefix = os.environ["BACKUP_PREFIX"].rstrip("/") + "/"
response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
objects = response.get("Contents") or []
if not objects:
    raise RuntimeError("No database backup object found")
latest = max(objects, key=lambda item: item["LastModified"])
key = latest["Key"]
head = s3.head_object(Bucket=bucket, Key=key)
s3.download_file(bucket, key, os.environ["backup_file"])
with open(os.environ["backup_file"], "rb") as handle:
    sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
expected_sha256 = (head.get("Metadata") or {}).get("sha256", "")
if head["ContentLength"] != os.path.getsize(os.environ["backup_file"]):
    raise RuntimeError("Downloaded backup size does not match S3 metadata")
if expected_sha256 and sha256 != expected_sha256:
    raise RuntimeError("Downloaded backup checksum does not match S3 metadata")
with open(os.environ["metadata_file"], "w", encoding="utf-8") as handle:
    json.dump({"bucket": bucket, "key": key, "bytes": head["ContentLength"], "sha256": sha256}, handle)
PY

docker volume create "$volume_name" >/dev/null
docker run -d --name "$container_name" --network none --shm-size=512m \
  -e POSTGRES_PASSWORD=restore_verify_only \
  -e POSTGRES_DB=life_infra_restore \
  -v "${volume_name}:/var/lib/postgresql/data" \
  "$POSTGIS_IMAGE" >/dev/null

for _attempt in $(seq 1 60); do
  if docker logs "$container_name" 2>&1 | grep -q "PostgreSQL init process complete" \
    && docker exec "$container_name" pg_isready -U postgres -d life_infra_restore >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec "$container_name" pg_isready -U postgres -d life_infra_restore >/dev/null
docker cp "$backup_file" "${container_name}:/tmp/latest.dump" >/dev/null
docker exec "$container_name" pg_restore --exit-on-error --no-owner --no-privileges \
  -U postgres -d life_infra_restore /tmp/latest.dump

counts="$(docker exec "$container_name" psql -At -U postgres -d life_infra_restore -c \
  "SELECT (SELECT count(*) FROM recommendations_place), (SELECT count(*) FROM recommendations_placetagevidence), PostGIS_Version();")"
place_count="${counts%%|*}"
remaining="${counts#*|}"
evidence_count="${remaining%%|*}"
postgis_version="${remaining#*|}"
if [ "${place_count:-0}" -le 0 ] || [ "${evidence_count:-0}" -le 0 ] || [ -z "$postgis_version" ]; then
  echo "Restore verification produced invalid counts: ${counts}" >&2
  exit 1
fi

export place_count evidence_count postgis_version
python3 - <<'PY'
import json
import os

with open(os.environ["metadata_file"], encoding="utf-8") as handle:
    result = json.load(handle)
result.update({
    "status": "restore_verified",
    "places": int(os.environ["place_count"]),
    "place_tag_evidences": int(os.environ["evidence_count"]),
    "postgis_version": os.environ["postgis_version"],
})
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
PY
