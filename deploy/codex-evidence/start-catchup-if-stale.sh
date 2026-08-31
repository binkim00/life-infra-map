#!/usr/bin/env bash
set -Eeuo pipefail

RUNTIME_DIR="${CODEX_EVIDENCE_RUNTIME_DIR:-/home/ubuntu/life-infra-map/runtime/codex-evidence}"
MAX_AGE_SECONDS="${CODEX_EVIDENCE_MAX_AGE_SECONDS:-50400}"
SERVICE="life-infra-map-codex-evidence.service"

if ! [[ "$MAX_AGE_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "CODEX_EVIDENCE_MAX_AGE_SECONDS must be a positive integer" >&2
  exit 1
fi

if systemctl is-active --quiet "$SERVICE"; then
  echo "$SERVICE is already active"
  exit 0
fi

latest_validation="$(find "$RUNTIME_DIR" -maxdepth 1 -type f -name 'validation-*.json' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
if [ -n "$latest_validation" ]; then
  latest_mtime="$(stat -c %Y "$latest_validation")"
  age_seconds="$(( $(date +%s) - latest_mtime ))"
  if [ "$age_seconds" -le "$MAX_AGE_SECONDS" ]; then
    echo "Latest successful validation is ${age_seconds}s old; catch-up is not required"
    exit 0
  fi
  echo "Latest successful validation is ${age_seconds}s old; starting catch-up"
else
  echo "No successful validation exists; starting catch-up"
fi

systemctl reset-failed "$SERVICE"
systemctl start --no-block "$SERVICE"
