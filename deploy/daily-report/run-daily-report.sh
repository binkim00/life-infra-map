#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${DAILY_REPORT_APP_ROOT:-/home/ubuntu/life-infra-map/app}"
API_CONTAINER="${DAILY_REPORT_API_CONTAINER:-life-infra-map-django-api}"
RUNTIME_DIR="${DAILY_REPORT_RUNTIME_DIR:-/home/ubuntu/life-infra-map/runtime/daily-reports}"
CODEX_DIR="${CODEX_EVIDENCE_RUNTIME_DIR:-/home/ubuntu/life-infra-map/runtime/codex-evidence}"
QUALITY_FILE="${QUALITY_REPORT_FILE:-/home/ubuntu/life-infra-map/runtime/quality-reports/latest-summary.json}"
SNS_TOPIC_ARN="${DAILY_REPORT_SNS_TOPIC_ARN:?DAILY_REPORT_SNS_TOPIC_ARN is required}"

if [ "$(docker inspect -f '{{.State.Running}}' "$API_CONTAINER" 2>/dev/null || true)" != "true" ]; then
  echo "API container is not running: $API_CONTAINER" >&2
  exit 1
fi

mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"
report_date="$(TZ=Asia/Seoul date +%F)"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
json_file="${RUNTIME_DIR}/collection-${run_id}.json"
message_file="${RUNTIME_DIR}/message-${run_id}.txt"

db_json="$(docker exec "$API_CONTAINER" python manage.py report_daily_collection --date "$report_date")"
codex_json='{"runs":0,"rows":0,"accepted":0,"needs_verification":0,"rejected":0,"saved":0,"primary_saved":0,"related_saved":0,"reasons":{}}'
mapfile -d '' validation_files < <(
  find "$CODEX_DIR" -maxdepth 1 -type f -name 'validation-*.json' \
    -newermt "${report_date} 00:00:00 +0900" -print0 2>/dev/null || true
)
if [ "${#validation_files[@]}" -gt 0 ]; then
  codex_json="$(jq -s '
    def merge_counts: reduce .[] as $item ({}; reduce ($item | to_entries[]) as $pair (.; .[$pair.key] = ((.[$pair.key] // 0) + $pair.value)));
    {runs:length, rows:(map(.rows // 0)|add), accepted:(map(.accepted // 0)|add),
     needs_verification:(map(.needs_verification // 0)|add), rejected:(map(.rejected // 0)|add),
     saved:(map(.saved // 0)|add), primary_saved:(map(.primary_saved // .saved // 0)|add),
     related_saved:(map(.related_saved // 0)|add), reasons:(map(.reasons // {})|merge_counts)}
  ' "${validation_files[@]}")"
fi
quality_json='{}'
if [ -r "$QUALITY_FILE" ]; then
  quality_json="$(cat "$QUALITY_FILE")"
fi

jq -n --argjson collection "$db_json" --argjson codex "$codex_json" --argjson quality "$quality_json" \
  '{collection:$collection, codex_runs:$codex, quality:$quality}' > "$json_file"
python3 "$APP_ROOT/deploy/daily-report/render_daily_report.py" "$json_file" "$message_file"
python3 "$APP_ROOT/deploy/daily-report/publish_daily_report.py" \
  --topic-arn "$SNS_TOPIC_ARN" \
  --report-date "$report_date" \
  --message-file "$message_file"

ln -sfn "$(basename "$json_file")" "$RUNTIME_DIR/latest.json"
ln -sfn "$(basename "$message_file")" "$RUNTIME_DIR/latest.txt"
find "$RUNTIME_DIR" -maxdepth 1 -type f \( -name 'collection-*.json' -o -name 'message-*.txt' \) -mtime +30 -delete
cat "$message_file"
