"""Explainable collection priority for restaurant registry rows.

This score never deletes or rejects a Place.  It only moves low-value, hard to
identify SEMAS rows behind consumer-facing restaurants in enrichment batches.
"""

import re


INSTITUTIONAL_TERMS = (
    "구내식당", "직원식당", "사내식당", "급식소", "단체급식", "위탁급식",
)
OPERATOR_TERMS = (
    "푸디스트", "푸드앤컬처", "아워홈", "후니드", "삼주외식", "외식산업",
    "본푸드서비스", "삼성웰스토리", "신세계푸드", "현대그린푸드",
    "씨제이프레시웨이", "동원홈푸드", "아라마크", "후레쉬케터링",
)
INSTITUTION_CONTEXT_TERMS = (
    "사업본부", "연구원", "대학교", "병원", "복지관", "세무서", "연수원",
)
LEGAL_NAME_RE = re.compile(r"(?:주식회사|유한회사|재단법인|사단법인|\(주\)|㈜)")
BRANCH_RE = re.compile(r"(?:점|지점|역점|본점|직영점)$")
CONVENIENCE_PREFIXES = (
    "씨유", "지에스25", "세븐일레븐", "이마트24", "미니스톱", "스토리웨이",
)
CAFE_OR_BAKERY_TERMS = (
    "카페", "커피", "coffee", "cafe", "베이커리", "제과", "도넛", "던킨",
    "파스쿠찌", "스타벅스", "투썸", "이디야", "컴포즈", "빽다방", "할리스",
)


def restaurant_collection_quality(place, *, identity_misses=0, successful_jobs=0):
    if place.category != "restaurant":
        return {"score": 0, "flags": []}

    name = re.sub(r"\s+", "", str(place.name or "")).strip()
    raw = place.raw if isinstance(place.raw, dict) else {}
    minor = str(raw.get("industry_minor_name") or raw.get("business_type") or "").strip()
    business_type = str(raw.get("business_type") or "").strip()
    dataset = str(raw.get("dataset") or "").strip().lower()
    normalized_name = str(place.name or "").strip()
    upper_name = normalized_name.upper()
    compact_name = re.sub(r"[\s_-]+", "", upper_name)
    score = 0
    flags = []

    if place.address and place.lat is not None and place.lng is not None:
        score += 4
        flags.append("complete_location")
    if place.source == "kakao_local" or getattr(place, "external_id", ""):
        score += 3
        flags.append("external_identity")
    if BRANCH_RE.search(name):
        score += 3
        flags.append("specific_branch")
    if minor:
        score += 2
        flags.append("specific_industry")
    if successful_jobs:
        score += min(10, successful_jobs * 5)
        flags.append("past_evidence_success")
    if dataset == "general_restaurant":
        score += 8
        flags.append("general_restaurant_registry")
    elif dataset == "commercial_store":
        score += 5
        flags.append("commercial_food_registry")
    elif "휴게음식점" in business_type:
        score -= 5
        flags.append("rest_food_service")

    if any(term in name for term in INSTITUTIONAL_TERMS):
        score -= 25
        flags.append("institutional_food_service")
    if any(term in name for term in OPERATOR_TERMS):
        score -= 12
        flags.append("contract_food_operator")
    if any(term in name for term in INSTITUTION_CONTEXT_TERMS):
        score -= 8
        flags.append("institutional_context")
    if LEGAL_NAME_RE.search(name):
        score -= 10
        flags.append("legal_entity_name")
    if len(name) <= 2:
        score -= 10
        flags.append("very_short_name")
    if (
        "편의점" in business_type
        or compact_name.startswith(("GS25", "CU"))
        or normalized_name.startswith(CONVENIENCE_PREFIXES)
    ):
        score -= 30
        flags.append("convenience_store")
    if any(term.lower() in normalized_name.lower() for term in CAFE_OR_BAKERY_TERMS):
        score -= 15
        flags.append("cafe_or_bakery")
    if identity_misses:
        score -= min(20, identity_misses * 6)
        flags.append("past_identity_mismatch")

    return {"score": max(-40, min(20, score)), "flags": flags}
