#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


REASON_LABELS = {
    "PAGE_UNAVAILABLE": "외부 페이지 접근 실패",
    "NO_FEATURE_EVIDENCE": "특징을 뒷받침하는 문장 없음",
    "LIVE_EVIDENCE_SPAN_MISMATCH": "재검사한 본문과 인용문 불일치",
    "NO_RESULT": "사용 가능한 검색 결과 없음",
    "IDENTITY_MISMATCH": "다른 장소 또는 지점",
    "AMBIGUOUS": "장소 식별 불확실",
    "LIVE_PLACE_IDENTITY_MISMATCH": "재검사 페이지의 장소 불일치",
    "LIVE_HTTP_403": "외부 페이지 접근 거부",
    "DUPLICATE_EVIDENCE": "이미 저장된 중복 근거",
    "LIVE_SOURCE_REJECT": "재검사 출처 정책 미통과",
    "STALE_ONLY": "오래된 근거만 발견",
}

COHORT_LABELS = {
    "cafe": "카페",
    "restaurant": "식당",
    "pharmacy": "약국",
    "toilet": "화장실",
    "parking": "주차장",
    "smoking_area": "흡연구역",
    "shelter": "쉼터",
    "walk": "산책",
    "shopping": "쇼핑",
    "unclassified": "미분류",
}
COHORT_ORDER = tuple(COHORT_LABELS)


def value(data, *keys, default=0):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current or current[key] is None:
            return default
        current = current[key]
    return current


def metric_text(metric):
    if not isinstance(metric, dict) or "value" not in metric or metric.get("measured") is False:
        return "집계 전"
    metric_value = metric.get("value")
    rendered = "{:.1f}%".format(metric_value * 100) if isinstance(metric_value, (int, float)) else str(metric_value)
    numerator = metric.get("numerator")
    denominator = metric.get("denominator")
    if numerator is not None and denominator is not None:
        rendered += " ({} / {})".format(numerator, denominator)
    return rendered


def release_gate_failures(quality):
    search = quality.get("search") or {}
    thresholds = value(quality, "release_gate", "thresholds", default={})
    checks = [
        ("검색마다 상위 5개 제공", value(search, "top_five_coverage_rate", "value", default=None), thresholds.get("top_five_coverage_rate"), lambda actual, target: actual >= target),
        ("각 조건 검색에 검증 근거 결과 포함", value(search, "feature_query_hit_at_5_rate", "value", default=None), thresholds.get("feature_query_hit_at_5_rate"), lambda actual, target: actual >= target),
        ("상위 5개 검증 근거 비율", value(search, "verified_feature_result_rate_at_5", "value", default=None), thresholds.get("verified_feature_result_rate_at_5_min"), lambda actual, target: actual >= target),
        ("추천 사유 투명성", value(search, "reason_transparency_rate", "value", default=None), thresholds.get("reason_transparency_rate"), lambda actual, target: actual >= target),
        ("필수 조건 위반 없음", value(search, "hard_violation_rate", "value", default=None), thresholds.get("hard_violation_rate_max"), lambda actual, target: actual <= target),
        ("검색 속도 p95", value(search, "latency_ms", "value", "p95", default=None), thresholds.get("latency_p95_ms_max"), lambda actual, target: actual <= target),
    ]
    return [label for label, actual, target, predicate in checks if actual is not None and target is not None and not predicate(actual, target)]


def cohort_quality_lines(quality):
    cohorts = quality.get("search_by_cohort") or {}
    keys = [key for key in COHORT_ORDER if key in cohorts]
    keys.extend(sorted(key for key in cohorts if key not in keys))
    lines = []
    for key in keys:
        metrics = cohorts.get(key) or {}
        latency = value(metrics, "latency_ms", "value", default={})
        lines.append(
            "- {}: 정상 {} / 목적 일치 {} / 상위 5개 {} / 조건 근거 {} / 위반 {} / p95 {}ms".format(
                COHORT_LABELS.get(key, key),
                metric_text(metrics.get("case_pass_rate")),
                metric_text(metrics.get("expected_identity_hit_at_3_rate")),
                metric_text(metrics.get("top_five_coverage_rate")),
                metric_text(metrics.get("feature_query_hit_at_5_rate")),
                metric_text(metrics.get("hard_violation_rate")),
                latency.get("p95", "집계 전") if isinstance(latency, dict) else "집계 전",
            )
        )
    return lines


def render_report(payload):
    collection = payload["collection"]
    naver = collection["naver"]
    web = collection["codex_web"]
    tags = collection["aggregate_tags"]
    runs = payload["codex_runs"]
    quality = payload.get("quality") or {}
    reasons = sorted((runs.get("reasons") or {}).items(), key=lambda item: -item[1])[:5]
    reason_text = ", ".join("{} {}건".format(REASON_LABELS.get(name, name), count) for name, count in reasons) or "없음"
    candidate_lines = []
    for page in (runs.get("candidate_pages") or [])[:5]:
        label = page.get("title") or page.get("url") or "제목 없음"
        candidate_lines.append("  · {} / {} / {}".format(page.get("place_name") or "장소 미상", page.get("target_tag") or "태그 미상", label))

    unknown = "집계 전"
    ready = value(quality, "release_gate", "ready", default=False)
    ready_text = "통과" if ready else "미통과 (연속 {}일)".format(value(quality, "release_gate", "consecutive_ready_days"))
    latency = value(quality, "search", "latency_ms", "value", default={})
    gate_failures = release_gate_failures(quality)
    cohort_lines = cohort_quality_lines(quality)
    lines = [
        "여기일지도 일일 수집 보고서 ({})".format(collection["date"]),
        "", "[네이버 블로그 수집]",
        "- 계획/완료: {} / {}곳".format(naver["planned_jobs"], naver["completed_jobs"]),
        "- 유효/근거 부족/실패: {} / {} / {}곳".format(naver["useful_jobs"], naver["insufficient_jobs"], naver["failed_jobs"]),
        "- API 요청: {}회 (제한 응답 {}회)".format(naver["api_requests"], naver["rate_limited_requests"]),
        "- 오늘 신규 근거: {}개, 장소 {}곳, 태그 종류 {}개".format(naver["new_evidence_rows"], naver["new_evidence_places"], naver["new_evidence_tags"]),
        "", "[Codex 웹 조사]",
        "- 집계 시작: {}".format(runs.get("window_start") or unknown),
        "- 실행/검사 후보: {}회 / {}개".format(runs["runs"], runs["rows"]),
        "- 판정(즉시 확정 가능/확인 필요/재조사/탈락): {} / {} / {} / {}개".format(runs["accepted"], runs["needs_verification"], runs.get("candidate_pending", 0), runs["rejected"]),
        "- 접근 실패 후보 보존: {}건".format(runs.get("candidates_preserved", 0)),
        "- DB에 근거 후보로 저장: {}개 (주 근거 {}, 관련 태그 파생 {}, 추가 검증 포함)".format(runs["saved"], runs.get("primary_saved", runs["saved"]), runs.get("related_saved", 0)),
        "- 오늘 DB 신규 근거: {}개, 장소 {}곳".format(web["new_evidence_rows"], web["new_evidence_places"]),
        "- 주요 검사 사유: {}".format(reason_text),
        *(["- 재조사 후보 페이지:", *candidate_lines] if candidate_lines else []),
        "", "[검색 품질 반영]",
        "- 오늘 신규 통합 태그: {}개, 장소 {}곳".format(tags["new_place_tags"], tags["new_tagged_places"]),
        "- 검색 가능 장소 증감: 카페 {}, 식당 {}".format(value(quality, "daily_delta", "cafe_searchable_places", default=unknown), value(quality, "daily_delta", "restaurant_searchable_places", default=unknown)),
        "- 검색마다 상위 5개 제공: {}".format(metric_text(value(quality, "search", "top_five_coverage_rate", default={}))),
        "- 상위 5개 건물 다양성: {}".format(metric_text(value(quality, "search", "top_five_building_diversity_rate", default={}))),
        "- 서로 다른 건물 3곳 이상인 검색 비율: {}".format(metric_text(value(quality, "search", "diverse_top_five_query_rate", default={}))),
        "- 조건 검색 중 검증 근거 결과가 1개 이상인 비율: {}".format(metric_text(value(quality, "search", "feature_query_hit_at_5_rate", default={}))),
        "- 상위 5개 중 조건을 검증 근거로 만족한 결과 비율: {}".format(metric_text(value(quality, "search", "verified_feature_result_rate_at_5", default={}))),
        "- 근거가 부족할 때 부족함을 밝힌 비율: {}".format(metric_text(value(quality, "search", "honest_no_hit_fallback_rate", default={}))),
        "- 추천 사유에 충족/부족 조건을 표시한 비율: {}".format(metric_text(value(quality, "search", "reason_transparency_rate", default={}))),
        "- 필수 조건 위반률: {}".format(metric_text(value(quality, "search", "hard_violation_rate", default={}))),
        "- 검색 속도: 평균 {}ms, p95 {}ms".format(latency.get("average", unknown), latency.get("p95", unknown)),
        *(["- 업종별 검색 품질:", *["  " + line for line in cohort_lines]] if cohort_lines else []),
        "- 1차 배포 게이트: {}".format(ready_text),
        "- 현재 미충족 항목: {}".format(", ".join(gate_failures) if gate_failures else "없음"),
        "", "생성 시각: {}".format(collection["generated_at"]),
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(render_report(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
