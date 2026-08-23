import re
import unicodedata
from collections import Counter

from django.db.models import Q
from django.utils import timezone

from recommendations.models import PlaceTagEvidence
from recommendations.services.canonical_tag_policy import canonical_tag_name
from recommendations.services.map_search import get_matching_categories
from recommendations.services.tag_utils import get_category_display_name


REGION_ALIASES = {
    "서울": ("서울", "서울특별시"),
    "부산": ("부산", "부산광역시"),
    "인천": ("인천", "인천광역시"),
    "대구": ("대구", "대구광역시"),
    "대전": ("대전", "대전광역시"),
    "광주": ("광주", "광주광역시"),
    "울산": ("울산", "울산광역시"),
}


def compact(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", value)


def explicit_query_categories(query):
    text = compact(query)
    ordered = (
        (("카페", "커피숍"), "cafe"),
        (("식당", "음식점", "혼밥", "밥먹", "밥을먹", "식사할"), "restaurant"),
        (("관광지", "관광명소"), "tourism"),
        (("공원",), "city_park"),
        (("도서관",), "library"),
        (("화장실",), "toilet"),
        (("주차장",), "parking"),
        (("대피소", "쉼터"), "shelter"),
        (("약국",), "pharmacy"),
        (("쇼핑몰", "백화점", "아울렛", "쇼핑할"), "shopping"),
        (("해수욕장", "바닷가", "해변"), "beach"),
        (("노래방",), "karaoke"),
    )
    return [category for terms, category in ordered if any(compact(term) in text for term in terms)]


def _required_condition_text(frame):
    values = []
    for condition in frame.get("structured_conditions") or frame.get("structuredConditions") or []:
        if isinstance(condition, dict) and condition.get("required"):
            values.append(condition.get("label") or condition.get("value") or "")
    return " ".join(values)


def objective_feature_requirements(query, frame):
    raw = " ".join([str(query or ""), _required_condition_text(frame)])
    text = compact(raw)
    requirements = []

    wifi = any(term in text for term in ("와이파이", "무선인터넷", "wifi"))
    if wifi and any(term in text for term in ("무료", "공공", "프리")):
        requirements.append({
            "code": "free_wifi", "label": "무료와이파이",
            "tags": {"무료와이파이"}, "categories": {"freewifi"},
        })
    free_use = any(term in text for term in ("무료로이용", "무료이용", "이용료무료", "입장료무료"))
    if free_use:
        requirements.append({
            "code": "free_use", "label": "무료이용",
            "tags": {"무료이용"}, "categories": set(),
        })
    if "주차" in text and any(term in text for term in ("주차가능", "주차할", "주차되는", "주차있는", "주차장")):
        requirements.append({
            "code": "parking", "label": "주차가능",
            "tags": {"주차가능"}, "categories": {"parking"} if "주차장" in text else set(),
        })
    if any(term in text for term in ("24시간", "이십사시간")):
        requirements.append({
            "code": "open_24_hours", "label": "24시간운영",
            "tags": {"24시간운영"}, "categories": set(),
        })
    elif any(term in text for term in ("밤늦게", "늦은밤", "야간운영", "심야")):
        requirements.append({
            "code": "open_late", "label": "야간운영",
            "tags": {"야간운영", "24시간운영"}, "categories": set(),
        })
    if any(term in text for term in ("문연", "영업중", "지금열", "현재열")):
        requirements.append({
            "code": "open_now", "label": "현재영업중",
            "tags": {"현재영업중"}, "categories": set(),
        })
    if any(term in text for term in ("작업할카페", "작업카페", "노트북작업", "노트북카페")):
        requirements.append({
            "code": "work_friendly", "label": "작업 관련 설비",
            "tags": {"노트북작업", "콘센트"}, "categories": set(),
        })
    if any(term in text for term in ("장애인시설", "장애인편의", "휠체어")):
        requirements.append({
            "code": "accessible", "label": "장애인시설",
            "tags": {"장애인시설"}, "categories": set(),
        })
    existing_codes = {item['code'] for item in requirements}
    for value in frame.get('required_features') or []:
        canonical = canonical_tag_name(value) or str(value or '').strip()
        if not canonical:
            continue
        if any(canonical in item.get('tags', set()) for item in requirements):
            continue
        code = f'explicit_feature:{canonical}'
        if code in existing_codes:
            continue
        requirements.append({
            'code': code,
            'label': canonical,
            'tags': {canonical},
            'categories': set(),
        })
        existing_codes.add(code)
    return requirements


def explicit_region(query):
    text = compact(query)
    for region, aliases in REGION_ALIASES.items():
        if any(compact(alias) in text for alias in aliases):
            return region
    return ""


def hard_gate_requirements(query, frame):
    frame = frame or {}
    query_categories = explicit_query_categories(query)
    frame_categories = []
    if not query_categories:
        direct_text = compact(" ".join([
            *(frame.get("target_objects") or []),
            *(frame.get("result_match_terms") or []),
        ]))
        for code in frame.get("candidate_category_codes") or []:
            if compact(code) in direct_text or compact(get_category_display_name(code)) in direct_text:
                frame_categories.append(code)
    return {
        "categories": list(dict.fromkeys(query_categories or frame_categories)),
        "features": objective_feature_requirements(query, frame),
        "region": explicit_region(query),
    }


def _candidate_categories(candidate):
    value = str(candidate.get("category") or "")
    direct = value if value in {
        "cafe", "restaurant", "tourism", "city_park", "library", "toilet",
        "parking", "shelter", "freewifi", "shopping", "pharmacy", "beach",
        "smoking_area", "karaoke",
    } else ""
    categories = set([direct] if direct else []) | set(get_matching_categories(value))
    name = compact(candidate.get("name"))
    if "약국" in name:
        categories.add("pharmacy")
    return categories


def _candidate_tags(candidate, active_tags):
    # A retrieval document or provider label can be stale. Objective hard
    # conditions are satisfied only by current positive evidence in our KB.
    return {
        str(value) for value in active_tags.get(candidate.get("place_id"), set()) if value
    }


def _active_tags_by_polarity(candidates, now):
    place_ids = {candidate.get("place_id") for candidate in candidates if candidate.get("place_id")}
    result = {"positive": {}, "negative": {}}
    if not place_ids:
        return result
    rows = PlaceTagEvidence.objects.filter(
        place_id__in=place_ids,
        polarity__in=("positive", "negative"),
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).values_list(
        "place_id", "tag__name", "polarity",
    )
    for place_id, tag_name, polarity in rows.iterator(chunk_size=1000):
        result[polarity].setdefault(place_id, set()).add(
            canonical_tag_name(tag_name) or tag_name
        )
    return result


def apply_common_hard_gate(candidates, query, frame, *, now=None):
    candidates = list(candidates or [])
    requirements = hard_gate_requirements(query, frame or {})
    active_tags = _active_tags_by_polarity(candidates, now or timezone.now())
    kept = []
    removed = []
    for candidate in candidates:
        violations = []
        categories = _candidate_categories(candidate)
        if requirements["categories"] and not categories.intersection(requirements["categories"]):
            violations.append({
                "type": "category", "required": requirements["categories"],
                "actual": sorted(categories),
            })
        region = requirements["region"]
        address = str(candidate.get("address") or candidate.get("detail_location") or "")
        if region and not any(address.startswith(alias) for alias in REGION_ALIASES[region]):
            violations.append({"type": "region", "required": region, "actual": address})
        tags = _candidate_tags(candidate, active_tags["positive"])
        negative_tags = _candidate_tags(candidate, active_tags["negative"])
        for requirement in requirements["features"]:
            if not (tags.intersection(requirement["tags"]) or categories.intersection(requirement["categories"])):
                contradicted = bool(negative_tags.intersection(requirement["tags"]))
                violations.append({
                    "type": "feature", "required": requirement["code"],
                    "label": requirement["label"], "actual_tags": sorted(tags),
                    "evidence_status": "contradicted" if contradicted else "unknown",
                })
        enriched = {
            **candidate,
            "hard_gate_passed": not violations,
            "hard_gate_violations": violations,
            "hard_gate_requirements": requirements,
            "hard_gate_active_tags": sorted(tags),
            "hard_gate_negative_tags": sorted(negative_tags),
        }
        if "pharmacy" in categories and compact(candidate.get("name")).find("약국") >= 0:
            enriched["source_category"] = candidate.get("category")
            enriched["category"] = "pharmacy"
            enriched["category_identity_inferred"] = True
        (removed if violations else kept).append(enriched)
    return kept, removed, {
        "requirements": requirements,
        "removed_count": len(removed),
        "removed_by_source": dict(Counter(
            str(row.get("candidate_source") or row.get("source") or "unknown") for row in removed
        )),
        "removed_by_type": dict(Counter(
            violation["type"] for row in removed for violation in row["hard_gate_violations"]
        )),
        "removed": [{
            "id": row.get("id"), "name": row.get("name"),
            "source": row.get("candidate_source") or row.get("source"),
            "category": row.get("category"), "violations": row["hard_gate_violations"],
        } for row in removed[:50]],
    }
