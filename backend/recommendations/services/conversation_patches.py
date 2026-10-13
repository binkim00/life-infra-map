"""Deterministic changes to conversation meaning, independent of retrieval."""
from copy import deepcopy
import re

from recommendations.services.canonical_tag_policy import canonical_tags_in_text

FEATURES = {
    "주차가능": ("주차",),
    "콘센트있음": ("콘센트", "충전"),
    "와이파이있음": ("와이파이", "wifi"),
    "조용함": ("조용", "한적"),
    "반려동물실내동반": ("반려견 실내", "반려동물 실내", "강아지 실내"),
    "단체석있음": ("단체석", "단체 좌석"),
}
TARGETS = {"카페": "cafe", "식당": "restaurant", "음식점": "restaurant", "도서관": "library", "공원": "city_park"}
LABELS = {"주차가능": "주차 가능", "단체석있음": "단체 이용", "반려동물실내동반": "반려견 실내동반"}

def text_value(value):
    if isinstance(value, dict):
        return str(value.get("value") or value.get("label") or value.get("name") or "")
    return str(value or "")

def compact(value):
    return re.sub(r"[^0-9a-z가-힣]", "", text_value(value).lower())

def condition_key(value):
    key = compact(value)
    for name, words in FEATURES.items():
        if key == compact(name) or any(compact(word) in key for word in words):
            return name
    tags = canonical_tags_in_text(text_value(value))
    return tags[0] if len(tags) == 1 else key

def plain_frame(frame):
    result = deepcopy(frame or {})
    for key in ("constraints", "exclusions", "target_objects", "candidate_place_types", "candidate_category_codes", "result_match_terms", "primary_search_queries", "secondary_search_queries", "required_features", "preferred_features"):
        result[key] = [text_value(item) for item in result.get(key, []) if text_value(item)]
    return result

def previous_frame(context):
    context = context or {}
    return context.get("place_intent_frame") or context.get("search_plan", {}).get("place_intent_frame") or context.get("pending_clarification_frame") or {}

def patch_frame(query, frame, *, source_turn=1, enhance_queries=True):
    """Return a patched frame and explicit actions, or None for unrecognized text."""
    query = str(query or "")
    raw = compact(query)
    updates = []
    mentioned = []
    for name, words in FEATURES.items():
        if name == "주차가능" and "parking" in [text_value(value) for value in (frame or {}).get("candidate_category_codes", [])]:
            continue
        positions = [query.lower().find(word.lower()) for word in words if word.lower() in query.lower()]
        if positions:
            mentioned.append((min(positions), name))
    mentioned.sort()
    for index, (start, name) in enumerate(mentioned):
        end = mentioned[index + 1][0] if index + 1 < len(mentioned) else len(query)
        clause = compact(query[start:end])
        if any(marker in clause for marker in ("대신", "취소", "빼줘", "빼", "제거", "없어도", "필요없")):
            updates.append((name, "remove", "include"))
        elif any(marker in clause for marker in ("없는곳", "불가한곳", "제외")):
            updates.append((name, "required", "exclude"))
        else:
            requirement = "preferred" if any(marker in clause for marker in ("있으면좋", "되면좋", "선호", "가능하면")) else "required"
            updates.append((name, requirement, "include"))
    target_match = re.search(r"(카페|식당|음식점|도서관|공원)\s*(?:말고|대신)\s*(카페|식당|음식점|도서관|공원)(?!도)", query)
    radius_match = re.search(r"(\d+(?:\.\d+)?)\s*(km|킬로|m|미터)\s*(?:안|이내|내)", query, re.I)
    closer = any(term in raw for term in ("더가까", "가까운데", "거리순"))
    from recommendations.services.area_gazetteer import resolve_area_coordinates_by_token
    location_text = re.sub(r"(?:으로|로)(?=\s|바꿔|변경|$)", "", query)
    location = resolve_area_coordinates_by_token(location_text) if frame and not any(word in raw for word in TARGETS) else None
    if not updates and not target_match and not radius_match and not closer and not location:
        return None
    result = plain_frame(frame)
    conditions = {}
    distances = []
    for item in result.get("structured_conditions") or []:
        if isinstance(item, dict) and item.get("type") == "distance":
            distances.append(deepcopy(item))
        elif isinstance(item, dict):
            key = condition_key(item.get("value") or item.get("label"))
            conditions[key] = {**item, "value": key, "label": item.get("label") or LABELS.get(key, key), "source_turn": item.get("source_turn") or max(source_turn - 1, 1), "requirement": item.get("requirement") or ("required" if item.get("required") else "preferred"), "polarity": item.get("polarity") or "include", "active": item.get("active", True)}
    for field, requirement in (("required_features", "required"), ("preferred_features", "preferred")):
        for value in result.get(field) or []:
            key = condition_key(value)
            if key not in conditions:
                conditions[key] = {"type": "feature", "value": key, "label": value, "required": requirement == "required", "requirement": requirement, "polarity": "include", "source_turn": max(source_turn - 1, 1), "active": True}
    actions = []
    for name, requirement, polarity in updates:
        old = conditions.get(name)
        # Broad inferred charging labels must not become an extra required condition.
        if name == "콘센트있음":
            conditions.pop(compact("작업/충전 가능"), None)
        actions.append({"type": "REMOVE_CONDITION" if requirement == "remove" else "CHANGE_REQUIREMENT" if old and old.get("active") else "ADD_CONDITION", "condition": name, "requirement": requirement, "polarity": polarity})
        conditions[name] = {"type": (old or {}).get("type") or "feature", "value": name, "label": (old or {}).get("label") or LABELS.get(name, name), "required": requirement == "required", "requirement": "preferred" if requirement == "remove" else requirement, "polarity": polarity, "source_turn": source_turn, "active": requirement != "remove"}
        result["constraints"] = [value for value in result["constraints"] if condition_key(value) != name and not (name == "콘센트있음" and compact(value) == compact("작업/충전 가능"))]
    active = [item for item in conditions.values() if item.get("active")]
    result["required_features"] = [item["label"] for item in active if item["requirement"] == "required" and item["polarity"] == "include"]
    result["preferred_features"] = [item["label"] for item in active if item["requirement"] == "preferred" and item["polarity"] == "include"]
    result["constraints"] = list(dict.fromkeys([*result["constraints"], *result["required_features"]]))
    result["structured_conditions"] = [*conditions.values(), *distances]
    result["structuredConditions"] = result["structured_conditions"]
    if target_match:
        target = target_match.group(2)
        result.update(target_objects=[target], candidate_place_types=[target], candidate_category_codes=[TARGETS[target]], result_match_terms=[target], primary_search_queries=[target], secondary_search_queries=[])
        actions.append({"type": "CHANGE_TARGET", "value": target})
    if enhance_queries and any(name == "조용함" and requirement == "required" for name, requirement, _ in updates) and result.get("target_objects"):
        target = result["target_objects"][0]
        result["primary_search_queries"] = list(dict.fromkeys([f"조용한 {target}", *result["primary_search_queries"]]))
    if radius_match:
        amount = float(radius_match.group(1)) * (1000 if radius_match.group(2).lower() in {"km", "킬로"} else 1)
        result["radius_m"] = min(max(int(amount), 300), 20000)
        actions.append({"type": "CHANGE_RADIUS", "value": result["radius_m"]})
    if closer or radius_match:
        result["ranking_policy"] = "distance_first"
        if closer:
            actions.append({"type": "CHANGE_SORT", "value": "distance_first"})
    if location:
        result.update(location_mode="explicit", locationMode="explicit", anchor_location=location[2], anchorLocation=location[2])
        actions.append({"type": "CHANGE_LOCATION", "value": location[2]})
    result["conversation_patch"] = actions
    return result, actions
