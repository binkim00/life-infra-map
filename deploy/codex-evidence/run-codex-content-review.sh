#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${CODEX_EVIDENCE_APP_ROOT:-/home/ubuntu/life-infra-map/app}"
RUNTIME_DIR="${CODEX_CONTENT_REVIEW_RUNTIME_DIR:-/home/ubuntu/life-infra-map/runtime/codex-evidence/content-review}"
CODEX_BIN="${CODEX_EVIDENCE_CODEX_BIN:-/home/ubuntu/.local/bin/codex}"
API_CONTAINER="${CODEX_EVIDENCE_API_CONTAINER:-life-infra-map-django-api}"
LIMIT="${CODEX_CONTENT_REVIEW_LIMIT:-10}"
APPLY="${CODEX_CONTENT_REVIEW_APPLY:-0}"

if ! [[ "$LIMIT" =~ ^([1-9]|1[0-9]|2[0-5])$ ]] || [[ "$APPLY" != 0 && "$APPLY" != 1 ]]; then
  echo 'Invalid review limit or apply flag' >&2
  exit 1
fi
if [[ "$(docker inspect -f '{{.State.Running}}' "$API_CONTAINER" 2>/dev/null || true)" != true ]]; then
  echo 'Django API container is not running' >&2
  exit 1
fi
mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
# Expired holds are historical only. Archive them before spending model tokens,
# while keeping their source and expiry unchanged and a durable review preimage.
if [[ "$APPLY" == 1 ]]; then
  docker exec "$API_CONTAINER" python manage.py archive_expired_pending_evidence \
    --apply --backup "/codex-content-review/expired-${run_id}.json"
else
  docker exec "$API_CONTAINER" python manage.py archive_expired_pending_evidence
fi
"$CODEX_BIN" login status >/dev/null
if [[ "$APPLY" == 1 ]]; then
  review_day="$(TZ=Asia/Seoul date +%Y%m%d)"
  shopt -s nullglob
  daily_markers=("$RUNTIME_DIR"/applied-run-"$review_day"-*.json)
  daily_used=0
  if ((${#daily_markers[@]})); then
    daily_used="$(jq -s '[.[] | .items] | add // 0' "${daily_markers[@]}")"
  fi
  if ((daily_used >= 5)); then
    echo 'Daily content review limit reached'
    exit 0
  fi
  if ((LIMIT > 5 - daily_used)); then
    LIMIT="$((5 - daily_used))"
  fi
fi
seed="seed-${run_id}.json"
result="result-${run_id}.json"
backup="backup-${run_id}.json"
script_dir="${APP_ROOT}/deploy/codex-evidence"
recent_ids="$(find "$RUNTIME_DIR" -maxdepth 1 -type f -name 'seed-*.json' -mtime -7 -print0 |
  xargs -0 -r jq -r '.items[]?.id // empty' | sort -nu | paste -sd, -)"

# The host directory is mounted in the Django container so the preimage is
# durable before any review or aggregate row is changed.
docker exec "$API_CONTAINER" python manage.py prepare_codex_content_review \
  --limit "$LIMIT" --live-page-excerpts --exclude-ids "$recent_ids" \
  --output "/codex-content-review/$seed"
item_count="$(jq '.items | length' "$RUNTIME_DIR/$seed")"
if [[ "$item_count" -eq 0 ]]; then
  echo 'No eligible pending content records'
  exit 0
fi

if ! "$CODEX_BIN" --ask-for-approval never exec \
  --ephemeral --ignore-user-config --sandbox read-only --skip-git-repo-check \
  --cd "$RUNTIME_DIR" \
  --output-schema "$script_dir/content-review-output.schema.json" \
  --output-last-message "$RUNTIME_DIR/$result" \
  "$(<"$script_dir/content-review-prompt.txt")" < "$RUNTIME_DIR/$seed" >/dev/null 2>/dev/null; then
  echo 'Codex content review failed; no decision applied' >&2
  exit 1
fi

if [[ "$APPLY" == 1 ]]; then
  # Reserve the day's capacity before the DB write. A failed run may use less
  # capacity, but can never cause a later retry to exceed the daily ceiling.
  marker="$RUNTIME_DIR/applied-run-$review_day-$run_id.json"
  jq -n --argjson items "$item_count" '{items: $items}' > "$marker.tmp"
  mv "$marker.tmp" "$marker"
  docker exec "$API_CONTAINER" python manage.py apply_codex_content_review \
    "/codex-content-review/$seed" "/codex-content-review/$result" \
    --apply --backup "/codex-content-review/$backup"
else
  docker exec "$API_CONTAINER" python manage.py apply_codex_content_review \
    "/codex-content-review/$seed" "/codex-content-review/$result"
fi
