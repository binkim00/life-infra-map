#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${CODEX_EVIDENCE_APP_ROOT:-/home/ubuntu/life-infra-map/app}"
API_CONTAINER="${CODEX_EVIDENCE_API_CONTAINER:-life-infra-map-django-api}"
RUNTIME_DIR="${CODEX_EVIDENCE_RUNTIME_DIR:-/home/ubuntu/life-infra-map/runtime/codex-evidence}"
CODEX_BIN="${CODEX_EVIDENCE_CODEX_BIN:-/home/ubuntu/.local/bin/codex}"
CAFE_LIMIT="${CODEX_EVIDENCE_CAFE_LIMIT:-25}"
RESTAURANT_LIMIT="${CODEX_EVIDENCE_RESTAURANT_LIMIT:-25}"
REVISIT_DAYS="${CODEX_EVIDENCE_REVISIT_DAYS:-1}"
DEPLOY_DIR="${APP_ROOT}/deploy/codex-evidence"

for required in "$CODEX_BIN" "$DEPLOY_DIR/research-prompt.txt" "$DEPLOY_DIR/codex-evidence-output.schema.json"; do
  if [ ! -e "$required" ]; then
    echo "Required file is missing: $required" >&2
    exit 1
  fi
done
if [ "$(docker inspect -f '{{.State.Running}}' "$API_CONTAINER" 2>/dev/null || true)" != "true" ]; then
  echo "API container is not running: $API_CONTAINER" >&2
  exit 1
fi
"$CODEX_BIN" login status >/dev/null

mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
seed_name="seed-${run_id}.json"
result_name="result-${run_id}.json"
validation_name="validation-${run_id}.json"
seed_file="${RUNTIME_DIR}/${seed_name}"
result_file="${RUNTIME_DIR}/${result_name}"
validation_file="${RUNTIME_DIR}/${validation_name}"
container_seed="/tmp/${seed_name}"
container_result="/tmp/${result_name}"
container_seed_csv="${container_seed%.json}.csv"

cleanup() {
  docker exec "$API_CONTAINER" rm -f -- "$container_seed" "$container_seed_csv" "$container_result" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! [[ "$REVISIT_DAYS" =~ ^[1-9][0-9]*$ ]]; then
  echo "CODEX_EVIDENCE_REVISIT_DAYS must be a positive integer" >&2
  exit 1
fi
exclude_ids="$(
  find "$RUNTIME_DIR" -maxdepth 1 -type f -name 'result-*.json' -mtime "-${REVISIT_DAYS}" -print0 \
    | xargs -0 -r jq -r '.results[]?.place_id // empty' 2>/dev/null \
    | sort -nu | paste -sd, - || true
)"
docker exec "$API_CONTAINER" python manage.py prepare_codex_web_research \
  --cafe "$CAFE_LIMIT" --restaurant "$RESTAURANT_LIMIT" \
  --exclude-place-ids "$exclude_ids" --preflight-source-hints --output "$container_seed"
docker cp "${API_CONTAINER}:${container_seed}" "$seed_file"

"$CODEX_BIN" --search --ask-for-approval never exec \
  --ephemeral \
  --ignore-user-config \
  -c model_reasoning_effort='"low"' \
  --sandbox read-only \
  --skip-git-repo-check \
  --cd "$RUNTIME_DIR" \
  --output-schema "$DEPLOY_DIR/codex-evidence-output.schema.json" \
  --output-last-message "$result_file" \
  "$(<"$DEPLOY_DIR/research-prompt.txt")" < "$seed_file" >/dev/null

jq -e '.results | type == "array"' "$result_file" >/dev/null
docker cp "$result_file" "${API_CONTAINER}:${container_result}"
docker exec "$API_CONTAINER" python manage.py validate_codex_web_evidence \
  "$container_result" --live-verify --apply | tee "$validation_file"

find "$RUNTIME_DIR" -maxdepth 1 -type f \( -name 'seed-*.json' -o -name 'result-*.json' -o -name 'validation-*.json' \) \
  -mtime +14 -delete
