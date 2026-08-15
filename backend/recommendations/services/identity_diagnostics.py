import re

from recommendations.services.naver_tag_evidence_provider import (
    address_identity_terms,
    compact,
    identity_assessment,
)


REGION_NAMES = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
GENERIC_NAMES = {
    "공립수목원", "근린공원", "어린이공원", "소공원", "공영주차장", "공중화장실",
    "화장실", "주차장", "경로당", "행정복지센터", "주민센터",
}


def place_region(place):
    address = str(place.address or "")
    return next((region for region in REGION_NAMES if address.startswith(region)), "")


def mentioned_regions(text):
    compact_text = compact(text)
    return [region for region in REGION_NAMES if region in compact_text]


def name_parts(name):
    return [compact(part) for part in re.findall(r"[0-9a-zA-Z가-힣]+", str(name or "")) if len(compact(part)) >= 2]


def branch_parts(name):
    return [part for part in name_parts(name)[1:] if part.endswith("점") or any(ch.isdigit() for ch in part)]


def classify_rejected_result(place, text, *, title=""):
    assessment = identity_assessment(place, text, title=title)
    signals = assessment["signals"]
    compact_text = compact(text)
    parts = name_parts(place.name)
    matched_parts = [part for part in parts if part in compact_text]
    expected_branches = branch_parts(place.name)
    region = place_region(place)
    result_regions = mentioned_regions(text)
    address_terms = address_identity_terms(place.address)
    address_matches = [term for term in address_terms if compact(term) in compact_text]

    if assessment["matched"]:
        reason = "REPRODUCED_AS_MATCH"
    elif expected_branches and parts and parts[0] in compact_text and not all(
        branch in compact_text for branch in expected_branches
    ):
        reason = "BRANCH_NAME_MISMATCH"
    elif region and result_regions and region not in result_regions:
        reason = "REGION_MISMATCH"
    elif signals.get("name") in {"exact", "all_terms"} and not address_matches:
        reason = "IDENTITY_THRESHOLD"
    elif matched_parts and address_matches:
        reason = "NAME_MISMATCH"
    elif matched_parts:
        reason = "INSUFFICIENT_IDENTITY_INFO"
    elif address_matches:
        reason = "NAME_MISMATCH"
    else:
        reason = "WRONG_SEARCH_RESULT"
    return {
        "reason": reason,
        "score": assessment["score"],
        "matched": assessment["matched"],
        "signals": signals,
        "place_region": region,
        "result_regions": result_regions,
        "address_matches": address_matches,
        "name_parts": parts,
        "matched_name_parts": matched_parts,
        "generic_name": compact(place.name) in {compact(value) for value in GENERIC_NAMES},
    }


def choose_place_failure(place, results):
    assessed = []
    for result in results:
        row = {
            **result,
            "identity": classify_rejected_result(place, result["text"], title=result.get("title", "")),
        }
        assessed.append(row)
    if not assessed:
        return {"reason": "NO_SEARCH_RESULT", "best": None, "results": []}
    best = max(
        assessed,
        key=lambda row: (
            row["identity"]["matched"],
            row["identity"]["score"],
            len(row["identity"]["address_matches"]),
        ),
    )
    return {"reason": best["identity"]["reason"], "best": best, "results": assessed}
