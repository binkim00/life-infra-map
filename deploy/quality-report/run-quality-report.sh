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
priority_name="priority-${run_id}.json"
container_coverage="/tmp/${coverage_name}"
container_evaluation="/tmp/${evaluation_name}"
container_priority="/tmp/${priority_name}"

cleanup() {
  docker exec "$API_CONTAINER" rm -f -- "$container_coverage" "$container_evaluation" "$container_priority" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker exec "$API_CONTAINER" python manage.py report_launch_evidence_quality --output "$container_coverage" >/dev/null
docker exec \
  -e CONVERSATIONAL_SEARCH_AI_ENABLED=false \
  -e AI_RERANK_ENABLED=false \
  -e AI_WEB_SEARCH_ENABLED=false \
  -e SEMANTIC_RETRIEVAL_ENABLED=false \
  -e SEMANTIC_CANDIDATE_INJECTION_ENABLED=false \
  -e KAKAO_REST_API_KEY= \
  "$API_CONTAINER" python manage.py evaluate_ai_search \
    --case-file "$CASE_FILE" --top 5 --no-log --output "$container_evaluation"
docker exec "$API_CONTAINER" python manage.py prioritize_launch_evidence \
  "$container_evaluation" --output "$container_priority" >/dev/null

docker cp "${API_CONTAINER}:${container_coverage}" "${RUNTIME_DIR}/${coverage_name}" >/dev/null
docker cp "${API_CONTAINER}:${container_evaluation}" "${RUNTIME_DIR}/${evaluation_name}" >/dev/null
docker cp "${API_CONTAINER}:${container_priority}" "${RUNTIME_DIR}/${priority_name}" >/dev/null

previous_summary='{}'
if [ -e "${RUNTIME_DIR}/latest-summary.json" ]; then
  previous_summary="$(cat "${RUNTIME_DIR}/latest-summary.json")"
fi

jq -n \
  --slurpfile coverage "${RUNTIME_DIR}/${coverage_name}" \
  --slurpfile evaluation "${RUNTIME_DIR}/${evaluation_name}" \
  --slurpfile priority "${RUNTIME_DIR}/${priority_name}" \
  --argjson previous "$previous_summary" \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg coverage_file "$coverage_name" \
  --arg evaluation_file "$evaluation_name" \
  --arg priority_file "$priority_name" \
  '{
    generated_at: $generated_at,
    artifacts: {coverage: $coverage_file, evaluation: $evaluation_file, priority: $priority_file},
    coverage: {
      cafe: $coverage[0].categories.cafe,
      restaurant: $coverage[0].categories.restaurant
    },
    search: $evaluation[0].metrics,
    collection_feedback: $priority[0],
    release_gate: {
      criteria_met_today: (
        $evaluation[0].metrics.top_five_coverage_rate.value == 1
        and $evaluation[0].metrics.hard_violation_rate.value == 0
        and $evaluation[0].metrics.reason_transparency_rate.value == 1
        and $evaluation[0].metrics.feature_query_hit_at_5_rate.value == 1
        and $evaluation[0].metrics.verified_feature_result_rate_at_5.value >= 0.6
        and $evaluation[0].metrics.latency_ms.value.p95 <= 3000
      ),
      thresholds: {
        top_five_coverage_rate: 1,
        hard_violation_rate_max: 0,
        reason_transparency_rate: 1,
        feature_query_hit_at_5_rate: 1,
        verified_feature_result_rate_at_5_min: 0.6,
        latency_p95_ms_max: 3000,
        consecutive_days_required: 3
      }
    },
    daily_delta: {
      baseline: ($previous.generated_at == null),
      cafe_searchable_places: (if $previous.generated_at then (($coverage[0].categories.cafe.recommendation_searchable_places // 0) - ($previous.coverage.cafe.recommendation_searchable_places // 0)) else null end),
      cafe_rich_places: (if $previous.generated_at then (($coverage[0].categories.cafe.recommendation_rich_places // 0) - ($previous.coverage.cafe.recommendation_rich_places // 0)) else null end),
      restaurant_searchable_places: (if $previous.generated_at then (($coverage[0].categories.restaurant.recommendation_searchable_places // 0) - ($previous.coverage.restaurant.recommendation_searchable_places // 0)) else null end),
      restaurant_rich_places: (if $previous.generated_at then (($coverage[0].categories.restaurant.recommendation_rich_places // 0) - ($previous.coverage.restaurant.recommendation_rich_places // 0)) else null end),
      feature_query_hit_at_5_rate: (if $previous.generated_at then (($evaluation[0].metrics.feature_query_hit_at_5_rate.value // 0) - ($previous.search.feature_query_hit_at_5_rate.value // 0)) else null end),
      verified_feature_result_rate_at_5: (if $previous.generated_at then (($evaluation[0].metrics.verified_feature_result_rate_at_5.value // 0) - ($previous.search.verified_feature_result_rate_at_5.value // 0)) else null end)
    }
  }
  | .release_gate.consecutive_ready_days = (
      if .release_gate.criteria_met_today
      then (($previous.release_gate.consecutive_ready_days // 0) + 1)
      else 0 end
    )
  | .release_gate.ready = (.release_gate.consecutive_ready_days >= 3)' > "${RUNTIME_DIR}/${summary_name}"

ln -sfn "$summary_name" "${RUNTIME_DIR}/latest-summary.json"
find "$RUNTIME_DIR" -maxdepth 1 -type f \( -name 'coverage-*.json' -o -name 'evaluation-*.json' -o -name 'priority-*.json' -o -name 'summary-*.json' \) -mtime +30 -delete
jq '{generated_at, release_gate, daily_delta, collection_feedback: {demand_places: .collection_feedback.demand_places, demand_tags: .collection_feedback.demand_tags, requests_created: .collection_feedback.requests_created, requests_updated: .collection_feedback.requests_updated, top_missing_tags: .collection_feedback.top_missing_tags}, search: {top_five_coverage_rate: .search.top_five_coverage_rate, top_five_building_diversity_rate: .search.top_five_building_diversity_rate, diverse_top_five_query_rate: .search.diverse_top_five_query_rate, feature_query_hit_at_5_rate: .search.feature_query_hit_at_5_rate, verified_feature_result_rate_at_5: .search.verified_feature_result_rate_at_5, honest_no_hit_fallback_rate: .search.honest_no_hit_fallback_rate, hard_violation_rate: .search.hard_violation_rate, reason_transparency_rate: .search.reason_transparency_rate, latency_ms: .search.latency_ms}}' "${RUNTIME_DIR}/${summary_name}"
