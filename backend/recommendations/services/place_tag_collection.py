"""Place-level collection profiles and multi-tag evidence extraction."""

from django.conf import settings

from recommendations.services.naver_search_provider import _clean_html, _request_channel, _safe_text
from recommendations.services.naver_tag_evidence_provider import (
    SEARCH_KEYWORDS,
    TAG_TERMS,
    identity_assessment,
    polarity_assessment,
    place_search_location_terms,
    search_location_terms,
)
from recommendations.services.evidence_scoring import evidence_confidence, parse_observed_date
from recommendations.services.tag_source_policy import NAVER_BLOG_SEARCH
from recommendations.services.provider_rate_limit import acquire_provider_slot
from recommendations.services.adaptive_tag_collection import targeted_profiles


COLLECTION_PROFILES = {
    "cafe": (
        ("work", ("노트북작업", "콘센트있음", "무료와이파이", "작업하기좋음", "장기체류좋음")),
        ("ambience", ("분위기좋음", "조용함", "혼자이용좋음", "데이트좋음", "대화하기좋음")),
        ("visit", ("전망좋음", "웨이팅적음")),
    ),
    "restaurant": (
        ("visit", ("혼밥좋음", "웨이팅적음", "데이트좋음", "대화하기좋음", "가족동반좋음")),
        ("ambience", ("분위기좋음", "조용함", "전망좋음")),
    ),
    "tourism": (
        ("experience", ("전망좋음", "분위기좋음", "데이트좋음", "조용함", "혼자이용좋음")),
        ("crowding", ("웨이팅적음", "대화하기좋음")),
    ),
    "city_park": (
        ("experience", ("조용함", "분위기좋음", "혼자이용좋음", "데이트좋음", "전망좋음", "산책좋음", "가족동반좋음", "야외활동좋음")),
        ("crowding", ("웨이팅적음", "대화하기좋음")),
    ),
    "library": (
        ("work", ("노트북작업", "콘센트있음", "무료와이파이", "작업하기좋음")),
        ("stay", ("조용함", "혼자이용좋음", "장기체류좋음")),
    ),
    "beach": (
        ("experience", ("전망좋음", "조용함", "가족동반좋음", "야외활동좋음")),
    ),
    "parking": (
        ("access", ("24시간운영", "장애인전용주차")),
        ("pricing", ("무료이용",)),
    ),
    "toilet": (
        ("access", ("휠체어접근", "장애인시설", "24시간운영")),
        ("condition", ("관리잘됨",)),
    ),
    "shelter": (
        ("access", ("24시간운영", "휠체어접근", "장애인시설")),
    ),
}

COLLECTION_PROFILES['restaurant'] = (
    (
        'visit',
        (
            '혼밥좋음', '웨이팅적음', '데이트좋음', '대화하기좋음',
            '가족동반좋음', '단체석있음', '예약가능', '개별룸있음',
            '유아의자있음', '유모차접근', '아이메뉴있음', '테이크아웃전문',
            '좌석없음', '예약필수', '웨이팅많음',
        ),
    ),
    (
        'ambience',
        (
            '분위기좋음', '조용함', '전망좋음', '넓은테이블',
            '좌석간격넓음', '편한좌석', '장기체류좋음', '엘리베이터있음',
            '무단차접근', '시간제한있음', '혼잡함', '소음큼',
            '계단접근만가능', '주차어려움',
        ),
    ),
    (
        'food_value',
        (
            '대표메뉴뚜렷함', '메뉴선택폭넓음', '여럿이먹기좋은메뉴', '가성비좋음',
        ),
    ),
)

COLLECTION_PROFILES['cafe'] = (
    (
        'work_stay',
        (
            '노트북작업', '콘센트있음', '와이파이있음', '무료와이파이',
            '작업하기좋음', '장기체류좋음', '시간제한있음',
        ),
    ),
    (
        'atmosphere_purpose',
        (
            '분위기좋음', '조용함', '소음큼', '혼잡함', '혼자이용좋음',
            '데이트좋음', '대화하기좋음', '사진찍기좋음',
        ),
    ),
    (
        'space',
        (
            '넓은테이블', '좌석간격넓음', '편한좌석', '개별룸있음',
            '단체석있음', '좌석없음', '자연채광좋음', '야외좌석',
        ),
    ),
    (
        'distinctiveness',
        (
            '전망좋음', '반려동물동반', '디저트특화', '커피맛좋음',
            '테이크아웃전문', '웨이팅적음', '웨이팅많음', '주차어려움',
            '계단접근만가능',
        ),
    ),
)


CATEGORY_ALIASES = {
    "bakery": "cafe",
    "food_service": "restaurant",
}

def canonical_category(category):
    value = str(category or "").strip().lower()
    return CATEGORY_ALIASES.get(value, value)


def collection_profile(category):
    return COLLECTION_PROFILES.get(canonical_category(category), ())


def requested_tags_for_category(category):
    return list(dict.fromkeys(
        tag_name
        for _, tag_names in collection_profile(category)
        for tag_name in tag_names
    ))


def planned_requests_for_category(category):
    return len(collection_profile(category))


def build_collection_query(place, keyword):
    location = " ".join(place_search_location_terms(place))
    return "{} {} {}".format(place.name, location, keyword).strip()


def collect_naver_place_evidence(
    place, requested_tags=None, *, allow_ai=False, strategy="standard", targeted_tags=None,
):
    """Collect multiple tag observations with one request per semantic pack."""
    requested = set(requested_tags or requested_tags_for_category(place.category))
    profiles = [
        (
            pack_name,
            SEARCH_KEYWORDS.get(tags[0], tags[0]),
            tuple(tag for tag in tags if tag in requested and tag in TAG_TERMS),
        )
        for pack_name, tags in collection_profile(place.category)
    ]
    profiles = [(name, keyword, tags) for name, keyword, tags in profiles if tags]
    if not profiles:
        return {"executed": True, "requests": 0, "evidences": [], "error": "unsupported_category"}

    if strategy in {"adaptive", "targeted_only"}:
        discovery = profiles[:1]
        all_allowed_tags = tuple(dict.fromkeys(tag for _, _, tags in profiles for tag in tags))
        additions = targeted_profiles(
            targeted_tags,
            all_allowed_tags,
            adopted_only=strategy != "targeted_only",
            max_stages=3 if strategy == "targeted_only" else 2,
        )
        if strategy == "targeted_only":
            profiles = additions
        else:
            seen_keywords = {keyword for _, keyword, _ in discovery}
            profiles = discovery + [row for row in additions if row[1] not in seen_keywords]

    evidences = []
    seen = set()
    requests_made = 0
    diagnostics = {
        "search_results": 0, "identity_matches": 0, "tag_expressions": 0,
        "short_snippets": 0, "strengths": {},
    }
    search_attempts = []
    ai_calls = 0
    ai_attempts = 0
    ai_metrics = {
        "grounded": 0, "invalid": 0, "input_tokens": 0, "output_tokens": 0,
        "total_tokens": 0, "cached_input_tokens": 0, "estimated_cost_usd": 0,
    }
    discovery_identity_matches = None
    for profile_index, (pack_name, keyword, tag_names) in enumerate(profiles):
        if strategy == "adaptive" and profile_index > 0 and not discovery_identity_matches:
            break
        # Naver treats a long list of semantic words as restrictive search terms.
        # Search with one representative word, then extract every tag in the pack
        # from the returned title/summary.
        query = build_collection_query(place, keyword)
        profile_evidence_start = len(evidences)
        query_stage = pack_name.rsplit("_", 1)[-1] if pack_name.startswith("target_") else "direct"
        attempt = {
            "place_id": place.id,
            "place_name": place.name,
            "category": place.category,
            "region": str(place.address or "").split(" ", 1)[0],
            "target_cluster": pack_name,
            "query_stage": query_stage,
            "actual_query": query,
            "results": [],
        }
        search_attempts.append(attempt)
        try:
            acquire_provider_slot("naver_search")
            payload = _request_channel("blog", query)
            requests_made += 1
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            return {
                "executed": True,
                "requests": requests_made + 1,
                "evidences": evidences,
                "error": "rate_limited" if status_code == 429 else "request_failed",
                "miss_reason": "OTHER",
                "diagnostics": diagnostics,
                "search_attempts": search_attempts,
            }

        for result_rank, item in enumerate((payload or {}).get("items") or [], start=1):
            diagnostics["search_results"] += 1
            title = _clean_html(item.get("title"), 180)
            summary = _clean_html(item.get("description"), 500)
            combined = "{} {}".format(title, summary)
            identity = identity_assessment(place, combined, title=title)
            result_audit = {
                "result_rank": result_rank,
                "title": title,
                "description": summary,
                "url": _safe_text(item.get("link"), 500),
                "identity_score": identity["score"],
                "identity_matched": identity["matched"],
                "extractions": [],
                "evidence_candidate": False,
                "rejection_reason": "",
            }
            attempt["results"].append(result_audit)
            if not identity["matched"]:
                result_audit["rejection_reason"] = "IDENTITY_MISMATCH"
                continue
            diagnostics["identity_matches"] += 1
            if len(combined.strip()) < 60:
                diagnostics["short_snippets"] += 1
            source_url = _safe_text(item.get("link"), 500)
            if not source_url.startswith(("http://", "https://")):
                result_audit["rejection_reason"] = "SOURCE_REJECT"
                continue
            snippet_evidences = 0
            for tag_name in tag_names:
                extraction = polarity_assessment(tag_name, combined, category=place.category)
                polarity = extraction["polarity"]
                result_audit["extractions"].append({
                    "tag": tag_name,
                    "polarity": polarity,
                    "strength": extraction.get("strength", "UNKNOWN"),
                    "positive_terms": extraction.get("positive_terms") or [],
                    "supporting_terms": extraction.get("supporting_terms") or [],
                    "weak_terms": extraction.get("weak_terms") or [],
                })
                key = (tag_name, source_url, polarity)
                if polarity == "unknown" or key in seen:
                    continue
                diagnostics["tag_expressions"] += 1
                strength = extraction.get("strength", "UNKNOWN")
                diagnostics["strengths"][strength] = int(diagnostics["strengths"].get(strength) or 0) + 1
                snippet_evidences += 1
                result_audit["evidence_candidate"] = True
                seen.add(key)
                observed_at = parse_observed_date(item.get("postdate"))
                confidence, confidence_factors = evidence_confidence(
                    source=NAVER_BLOG_SEARCH,
                    identity_score=identity["score"],
                    clarity_score=extraction["clarity_score"],
                    observed_at=observed_at,
                )
                evidences.append({
                    "tag_name": tag_name,
                    "polarity": polarity,
                    "evidence_summary": summary or title,
                    "source_url": source_url,
                    "source_title": title,
                    "observed_date": item.get("postdate") or None,
                    "confidence": confidence,
                    "identity": identity,
                    "extraction": extraction,
                    "confidence_factors": confidence_factors,
                    "raw": {"channel": "naver_blog", "query": query, "pack": pack_name, "query_stage": query_stage},
                })
            if (
                allow_ai
                and snippet_evidences == 0
                and identity["score"] >= getattr(settings, "TAG_COLLECTION_AI_MIN_IDENTITY_SCORE", 70)
                and ai_attempts < getattr(settings, "TAG_COLLECTION_AI_MAX_CALLS_PER_PLACE", 1)
            ):
                from recommendations.services.canonical_ai_evidence_extractor import (
                    extract_canonical_tags_from_evidence_detailed,
                )
                ai_attempts += 1
                extraction_result = extract_canonical_tags_from_evidence_detailed(combined, tag_names)
                metrics = extraction_result.get("metrics") or {}
                ai_calls += int(metrics.get("attempted") or 0)
                for key in (
                    "grounded", "invalid", "input_tokens", "output_tokens",
                    "total_tokens", "cached_input_tokens",
                ):
                    ai_metrics[key] += int(metrics.get(key) or 0)
                ai_metrics["estimated_cost_usd"] = round(
                    ai_metrics["estimated_cost_usd"] + float(metrics.get("estimated_cost_usd") or 0), 8,
                )
                if metrics.get("model"):
                    ai_metrics["model"] = metrics["model"]
                for extracted in extraction_result.get("matches") or []:
                    key = (extracted["tag_name"], source_url, extracted["polarity"])
                    if key in seen:
                        continue
                    seen.add(key)
                    diagnostics["tag_expressions"] += 1
                    confidence, confidence_factors = evidence_confidence(
                        source=NAVER_BLOG_SEARCH,
                        identity_score=identity["score"],
                        clarity_score=65,
                        observed_at=parse_observed_date(item.get("postdate")),
                    )
                    evidences.append({
                        "tag_name": extracted["tag_name"],
                        "polarity": extracted["polarity"],
                        "evidence_summary": extracted["evidence_span"],
                        "source_url": source_url,
                        "source_title": title,
                        "observed_date": item.get("postdate") or None,
                        "confidence": confidence,
                        "identity": identity,
                        "extraction": {"method": "ai", "strength": "SUPPORTING", "evidence_span": extracted["evidence_span"]},
                        "confidence_factors": confidence_factors,
                        "raw": {"channel": "naver_blog", "query": query, "pack": pack_name, "query_stage": query_stage},
                    })
                    result_audit["evidence_candidate"] = True
                    result_audit["extractions"].append({
                        "tag": extracted["tag_name"], "polarity": extracted["polarity"],
                        "strength": "SUPPORTING", "method": "ai",
                    })

            if result_audit["evidence_candidate"]:
                result_audit["rejection_reason"] = ""
            elif any(row.get("strength") == "WEAK" for row in result_audit["extractions"]):
                result_audit["rejection_reason"] = "WEAK_FEATURE"
            else:
                result_audit["rejection_reason"] = "NO_FEATURE"

        if profile_index == 0:
            discovery_identity_matches = diagnostics["identity_matches"]
        if pack_name.startswith("target_") and len(evidences) > profile_evidence_start:
            break

    miss_reason = ""
    if not evidences:
        if diagnostics["search_results"] == 0:
            miss_reason = "NO_SEARCH_RESULT"
        elif diagnostics["identity_matches"] == 0:
            miss_reason = "IDENTITY_MISMATCH"
        elif diagnostics["short_snippets"] == diagnostics["identity_matches"]:
            miss_reason = "INSUFFICIENT_SNIPPET"
        elif diagnostics["tag_expressions"] == 0:
            miss_reason = "NO_TAG_EXPRESSION"
        else:
            miss_reason = "OTHER"
    return {
        "executed": True,
        "requests": requests_made,
        "evidences": evidences,
        "error": "" if evidences else "insufficient_evidence",
        "miss_reason": miss_reason,
        "diagnostics": diagnostics,
        "ai_calls": ai_calls,
        "ai_metrics": ai_metrics,
        "search_attempts": search_attempts,
    }
