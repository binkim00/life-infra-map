"""Evidence-backed smoking metadata derived without expanding the Place schema."""

FACILITY_TAGS = {
    "지정흡연구역": "designated_smoking_area",
    "실외흡연구역": "designated_smoking_area",
    "개방형흡연구역": "designated_smoking_area",
    "흡연부스": "smoking_booth",
    "부스형흡연구역": "smoking_booth",
    "흡연실": "smoking_room",
    "실내흡연실": "smoking_room",
    "재떨이위치": "ashtray_only",
}

HIDDEN_BY_DEFAULT = {"STALE", "POSSIBLY_REMOVED"}


def _tag_names(place):
    return {item.tag.name for item in place.place_tags.all() if item.status != "rejected"}


def _evidence(place):
    return list(place.tag_evidence.all())


def derive_smoking_metadata(place):
    if place.category != "smoking_area":
        return None

    raw = place.raw or {}
    tags = _tag_names(place)
    evidence = _evidence(place)
    facility_type = next((value for name, value in FACILITY_TAGS.items() if name in tags), None)
    if not facility_type:
        raw_type = raw.get("facility_type")
        raw_type_text = " ".join(str(value) for value in raw_type.values()) if isinstance(raw_type, dict) else str(raw_type or "")
        indoor_outdoor = str(raw.get("indoor_outdoor") or "")
        if raw_type in {"designated_smoking_area", "smoking_booth", "smoking_room", "ashtray_only", "smoking_area_candidate"}:
            facility_type = raw_type
        elif raw.get("흡연실여부") == "Y" or "room" in raw_type_text.lower():
            facility_type = "smoking_room"
        elif indoor_outdoor == "booth" or "booth" in raw_type_text.lower() or "부스" in raw_type_text:
            facility_type = "smoking_booth"
        else:
            facility_type = "designated_smoking_area"

    contexts = [item.context or {} for item in evidence]
    explicit_statuses = [ctx.get("verification_status") for ctx in contexts if ctx.get("verification_status")]
    if facility_type == "ashtray_only":
        verification_level, permission = "ASHTRAY_ONLY", "unknown"
    elif explicit_statuses:
        verification_level = {
            "HIGH_CONFIDENCE_WEB": "WEB_VERIFIED",
            "NEEDS_VERIFICATION": "UNVERIFIED",
        }.get(explicit_statuses[0], explicit_statuses[0])
        permission = "confirmed" if verification_level in {"VERIFIED", "VERIFIED_OFFICIAL", "VERIFIED_FACILITY"} else "unverified"
    elif "연제구_흡연실" in place.source:
        verification_level, permission = "PUBLIC_DATA", "confirmed"
    elif raw.get("source") == "official_airport" and raw.get("is_operating") is True:
        verification_level, permission = "PUBLIC_DATA", "confirmed"
    else:
        verification_level, permission = "UNVERIFIED", "unverified"

    observed_dates = [item.observed_at.date() for item in evidence if item.observed_at]
    last_verified = max(observed_dates).isoformat() if observed_dates else (place.source_updated_at.isoformat() if place.source_updated_at else None)
    confidence_values = [item.confidence for item in evidence if item.polarity == "positive"]
    confidence = max(confidence_values) if confidence_values else (75 if verification_level == "PUBLIC_DATA" else place.data_quality_score)
    source_summary = {
        "type": "evidence" if evidence else ("public_data" if verification_level == "PUBLIC_DATA" else "place_source"),
        "name": place.source_name or place.source,
        "count": len(evidence) or 1,
    }
    return {
        "facility_type": facility_type,
        "smoking_permission": permission,
        "verification_level": verification_level,
        "last_verified_at": last_verified,
        "evidence_confidence": confidence,
        "source_summary": source_summary,
        "default_visible": verification_level not in HIDDEN_BY_DEFAULT,
        "location_description": raw.get("location_description") or place.detail_location,
        "location_landmark": raw.get("location_landmark", ""),
        "location_directions": raw.get("location_directions", ""),
        "location_accuracy": raw.get("location_accuracy") or raw.get("coordinate_accuracy") or "UNKNOWN",
        "location_source_url": raw.get("location_source_url", ""),
        "location_evidence_span": raw.get("location_evidence_span", ""),
    }


def matches_smoking_filters(metadata, *, facility_type="", verification="", include_stale=False):
    if not metadata:
        return False
    if not include_stale and not metadata["default_visible"]:
        return False
    if facility_type and metadata["facility_type"] != facility_type:
        return False
    if verification:
        requested = {value.strip().upper() for value in verification.split(",") if value.strip()}
        if metadata["verification_level"].upper() not in requested:
            return False
    return True
