import re
import unicodedata
from difflib import SequenceMatcher

from recommendations.services.map_search import calculate_distance_m


CORPORATE_TERMS = ("주식회사", "유한회사", "재단법인", "사단법인")
PHONE_KEYS = {
    "전화번호", "소재지전화", "사업장전화번호", "전화", "연락처",
    "sitetel", "telno", "phone", "phonenumber",
}
CATEGORY_GROUPS = {
    "cafe": {"CE7"},
    "bakery": {"CE7", "FD6"},
    "restaurant": {"FD6"},
    "food_service": {"CE7", "FD6"},
    "tourism": {"AT4", "CT1"},
    "library": {"CT1"},
}


def clean_text(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def normalize_name(value):
    text = clean_text(value).lower()
    for term in CORPORATE_TERMS:
        text = text.replace(term, "")
    text = re.sub(r"\(\s*주\s*\)|㈜", "", text)
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def name_tokens(value):
    text = clean_text(value).lower()
    text = re.sub(r"\(\s*주\s*\)|㈜", " ", text)
    return [token for token in re.findall(r"[0-9a-z가-힣]+", text) if token not in CORPORATE_TERMS]


def branch_tokens(value):
    tokens = name_tokens(value)
    return {
        token for token in tokens
        if token.endswith(("점", "지점", "센터점", "역점")) and len(token) >= 2
    }


def normalize_address(value):
    text = clean_text(value).lower()
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"\b\d{5}\b", " ", text)
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def address_tokens(value):
    text = clean_text(value).lower()
    return set(re.findall(r"[0-9a-z가-힣]+", re.sub(r"\(.*?\)", " ", text)))


def normalize_phone(value):
    digits = re.sub(r"\D", "", clean_text(value))
    if digits.startswith("82"):
        digits = "0" + digits[2:]
    return digits


def source_phone(record):
    raw = record.raw if isinstance(record.raw, dict) else {}
    for key, value in raw.items():
        normalized_key = re.sub(r"[^0-9a-z가-힣]", "", clean_text(key).lower())
        if normalized_key in PHONE_KEYS and normalize_phone(value):
            return normalize_phone(value)
    return ""


def _similarity(left, right):
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _token_similarity(left, right):
    left_tokens = address_tokens(left)
    right_tokens = address_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _name_score(source_name, candidate_name):
    source = normalize_name(source_name)
    candidate = normalize_name(candidate_name)
    if not source or not candidate:
        return 0.0
    if source == candidate:
        return 44.0
    shorter, longer = sorted((source, candidate), key=len)
    containment = len(shorter) / max(1, len(longer)) if shorter in longer else 0
    similarity = _similarity(source, candidate)
    if containment >= 0.8:
        return 39.0
    if similarity >= 0.9:
        return 37.0
    if containment >= 0.65 or similarity >= 0.8:
        return 31.0
    if similarity >= 0.68:
        return 20.0
    return max(0.0, round(similarity * 20, 2))


def _address_score(record, candidate):
    sources = [record.road_address, record.address]
    targets = [candidate.get("road_address_name"), candidate.get("address_name")]
    best = 0.0
    for source in sources:
        normalized_source = normalize_address(source)
        if not normalized_source:
            continue
        for target in targets:
            normalized_target = normalize_address(target)
            if not normalized_target:
                continue
            if normalized_source == normalized_target:
                best = max(best, 27.0)
                continue
            shorter, longer = sorted((normalized_source, normalized_target), key=len)
            containment = len(shorter) / max(1, len(longer)) if shorter in longer else 0
            token_similarity = _token_similarity(source, target)
            if containment >= 0.82:
                best = max(best, 24.0)
            elif token_similarity >= 0.65:
                best = max(best, 20.0)
            elif token_similarity >= 0.45:
                best = max(best, 13.0)
            elif token_similarity >= 0.25:
                best = max(best, 6.0)
    return best


def _distance_score(distance_m):
    if distance_m is None:
        return 0.0
    if distance_m <= 30:
        return 24.0
    if distance_m <= 80:
        return 22.0
    if distance_m <= 150:
        return 18.0
    if distance_m <= 300:
        return 11.0
    if distance_m <= 700:
        return 4.0
    if distance_m <= 1200:
        return 0.0
    return -15.0


def _candidate_coordinates(candidate):
    try:
        return float(candidate.get("y")), float(candidate.get("x"))
    except (TypeError, ValueError):
        return None


def score_candidate(record, candidate, *, source_coordinates=None):
    candidate_coordinates = _candidate_coordinates(candidate)
    distance_m = None
    if source_coordinates and candidate_coordinates:
        distance_m = calculate_distance_m(*source_coordinates, *candidate_coordinates)

    name_score = _name_score(record.name, candidate.get("place_name"))
    address_score = _address_score(record, candidate)
    distance_score = _distance_score(distance_m)
    record_phone = source_phone(record)
    candidate_phone = normalize_phone(candidate.get("phone"))
    phone_score = 0.0
    phone_conflict = False
    if record_phone and candidate_phone:
        if record_phone == candidate_phone:
            phone_score = 10.0
        else:
            phone_score = -8.0
            phone_conflict = True

    expected_groups = CATEGORY_GROUPS.get(record.category, set())
    candidate_group = clean_text(candidate.get("category_group_code"))
    category_score = 4.0 if expected_groups and candidate_group in expected_groups else 0.0
    if expected_groups and candidate_group and candidate_group not in expected_groups:
        category_score = -5.0

    source_branches = branch_tokens(record.name)
    candidate_branches = branch_tokens(candidate.get("place_name"))
    names_equivalent = normalize_name(record.name) == normalize_name(candidate.get("place_name"))
    branch_conflict = bool(
        not names_equivalent
        and source_branches
        and candidate_branches
        and source_branches.isdisjoint(candidate_branches)
    )
    branch_score = -30.0 if branch_conflict else 0.0

    total = max(0.0, min(100.0, name_score + address_score + distance_score + phone_score + category_score + branch_score))
    return {
        "candidate": candidate,
        "score": round(total, 2),
        "distance_m": distance_m,
        "details": {
            "name": name_score,
            "address": address_score,
            "distance": distance_score,
            "phone": phone_score,
            "category": category_score,
            "branch": branch_score,
            "branch_conflict": branch_conflict,
            "phone_conflict": phone_conflict,
        },
    }


def choose_match(record, candidates, *, source_coordinates=None, confirmed_score=82, min_margin=12):
    scored = sorted(
        (score_candidate(record, candidate, source_coordinates=source_coordinates) for candidate in candidates),
        key=lambda item: (-item["score"], item["distance_m"] if item["distance_m"] is not None else 10**9),
    )
    if not scored:
        return {"status": "unmatched", "top": None, "margin": 0, "scored": []}

    top = scored[0]
    runner_up_score = scored[1]["score"] if len(scored) > 1 else 0
    margin = round(top["score"] - runner_up_score, 2)
    details = top["details"]
    has_location_proof = details["address"] >= 20 or (
        top["distance_m"] is not None and top["distance_m"] <= 150
    ) or details["phone"] > 0
    hard_conflict = details["branch_conflict"] or details["phone_conflict"]
    confirmable = (
        top["score"] >= confirmed_score
        and margin >= min_margin
        and details["name"] >= 31
        and has_location_proof
        and not hard_conflict
    )
    if confirmable:
        status = "confirmed"
    elif top["score"] >= 58:
        status = "ambiguous"
    else:
        status = "unmatched"
    return {"status": status, "top": top, "margin": margin, "scored": scored}


def build_search_queries(record):
    name = clean_text(record.name)
    address = clean_text(record.road_address or record.address)
    area = clean_text(" ".join(part for part in (record.sido_name, record.sigungu_name) if part))
    queries = []
    for query in (f"{name} {address}", f"{name} {area}", name):
        query = re.sub(r"\s+", " ", query).strip()
        if query and query not in queries:
            queries.append(query[:500])
    return queries


def candidate_snapshot(scored_item):
    candidate = scored_item["candidate"]
    return {
        "id": clean_text(candidate.get("id")),
        "place_name": clean_text(candidate.get("place_name")),
        "address_name": clean_text(candidate.get("address_name")),
        "road_address_name": clean_text(candidate.get("road_address_name")),
        "phone": clean_text(candidate.get("phone")),
        "category_group_code": clean_text(candidate.get("category_group_code")),
        "x": clean_text(candidate.get("x")),
        "y": clean_text(candidate.get("y")),
        "place_url": clean_text(candidate.get("place_url")),
        "score": scored_item["score"],
        "distance_m": scored_item["distance_m"],
        "score_details": scored_item["details"],
    }
