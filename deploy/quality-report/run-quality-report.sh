#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${QUALITY_REPORT_APP_ROOT:-/home/ubuntu/life-infra-map/app}"
API_CONTAINER="${QUALITY_REPORT_API_CONTAINER:-life-infra-map-django-api}"
RUNTIME_DIR="${QUALITY_REPORT_RUNTIME_DIR:-/home/ubuntu/life-infra-map/runtime/quality-reports}"
CASE_FILE="recommendations/evaluation_cases/busan_launch_quality_24.json"

if [ "$(docker inspect -f '{{.State.Running}}' "$API_CONTAINER" 2>/dev/null || true)" != "true" ]; then
  echo "API container is not running: $API_CONTAINER" >&2
  exit 1
fi

mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
coverage_name="coverage-${run_id}.json"
evaluation_name="evaluation-${run_id}.json"
summary_name="summary-${run_id}.json"
container_coverage="/tmp/${coverage_name}"
container_evaluation="/tmp/${evaluation_name}"

cleanup() {
  docker exec "$API_CONTAINER" rm -f -- "$container_coverage" "$container_evaluation" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker exec "$API_CONTAINER" python manage.py report_city_food_coverage --output "$container_coverage" >/dev/null
docker exec \
  -e CONVERSATIONAL_SEARCH_AI_ENABLED=false \
  -e AI_RERANK_ENABLED=false \
  -e AI_WEB_SEARCH_ENABLED=false \
  -e SEMANTIC_RETRIEVAL_ENABLED=false \
  -e SEMANTIC_CANDIDATE_INJECTION_ENABLED=false \
  -e KAKAO_REST_API_KEY= \
  "$API_CONTAINER" python manage.py evaluate_ai_search \
    --case-file "$CASE_FILE" --top 5 --no-log --output "$container_evaluation"

docker cp "${API_CONTAINER}:${container_coverage}" "${RUNTIME_DIR}/${coverage_name}" >/dev/null
docker cp "${API_CONTAINER}:${container_evaluation}" "${RUNTIME_DIR}/${evaluation_name}" >/dev/null

jq -n \
  --slurpfile coverage "${RUNTIME_DIR}/${coverage_name}" \
  --slurpfile evaluation "${RUNTIME_DIR}/${evaluation_name}" \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg coverage_file "$coverage_name" \
  --arg evaluation_file "$evaluation_name" \
  '{
    generated_at: $generated_at,
    artifacts: {coverage: $coverage_file, evaluation: $evaluation_file},
    coverage: {
      cafe: $coverage[0].regions["부산"].cafe,
      restaurant: $coverage[0].regions["부산"].restaurant
    },
    search: $evaluation[0].metrics,
    release_gate: {
      ready: (
        $evaluation[0].metrics.top_five_coverage_rate.value == 1
        and $evaluation[0].metrics.hard_violation_rate.value == 0
        and $evaluation[0].metrics.reason_transparency_rate.value == 1
        and $evaluation[0].metrics.feature_query_hit_at_5_rate.value == 1
        and $evaluation[0].metrics.verified_feature_result_rate_at_5.value >= 0.6
      ),
      thresholds: {
        top_five_coverage_rate: 1,
        hard_violation_rate_max: 0,
        reason_transparency_rate: 1,
        feature_query_hit_at_5_rate: 1,
        verified_feature_result_rate_at_5_min: 0.6
      }
    }
  }' > "${RUNTIME_DIR}/${summary_name}"

ln -sfn "$summary_name" "${RUNTIME_DIR}/latest-summary.json"
find "$RUNTIME_DIR" -maxdepth 1 -type f \( -name 'coverage-*.json' -o -name 'evaluation-*.json' -o -name 'summary-*.json' \) -mtime +30 -delete
jq '{generated_at, release_gate, search: {top_five_coverage_rate: .search.top_five_coverage_rate, feature_query_hit_at_5_rate: .search.feature_query_hit_at_5_rate, verified_feature_result_rate_at_5: .search.verified_feature_result_rate_at_5, honest_no_hit_fallback_rate: .search.honest_no_hit_fallback_rate, hard_violation_rate: .search.hard_violation_rate, reason_transparency_rate: .search.reason_transparency_rate}}' "${RUNTIME_DIR}/${summary_name}"
