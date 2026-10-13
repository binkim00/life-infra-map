"""Conservative external candidate to internal Place lookup.

Candidate deduplication is intentionally separate: a plausible nearby name
must never transfer another Place's evidence into a search result.
"""

import math

from django.db.models import Q

from recommendations.models import Place
from recommendations.services.commercial_place_registry import normalize_address, normalize_name
from recommendations.services.smoking_area_data import calculate_distance_m


def assess_identity(candidate, place):
    name = normalize_name(candidate.get("name"))
    place_name = normalize_name(place.name)
    if not name or not place_name or name != place_name:
        return "none"
    candidate_address = normalize_address(candidate.get("address"))
    addresses = {
        normalize_address(place.address), normalize_address(place.detail_location),
    } - {""}
    exact_address = bool(candidate_address and candidate_address in addresses)
    lat, lng = candidate.get("lat"), candidate.get("lng")
    distance = None
    if lat is not None and lng is not None:
        try:
            distance = calculate_distance_m(float(lat), float(lng), place.lat, place.lng)
        except (TypeError, ValueError):
            pass
    # A matching street address or very close coordinates is required in
    # addition to the full name. Disagreeing coordinates veto an address hit.
    if exact_address and (distance is None or distance <= 100):
        return "exact_name_address"
    if distance is not None and distance <= 30 and (not candidate_address or exact_address):
        return "exact_name_coordinates"
    return "none"


def lookup_internal_place(candidate):
    """Return (Place or None, reason) with bounded lookup and no fuzzy merge."""
    lat, lng = candidate.get("lat"), candidate.get("lng")
    if lat is not None or lng is not None:
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return None, "invalid_coordinates"
        if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
            return None, "invalid_coordinates"
    external_id = str(candidate.get("external_id") or "").strip()
    if candidate.get("candidate_source") == "kakao" and external_id:
        direct = list(Place.objects.filter(source="kakao_local", external_id=external_id)[:2])
        if len(direct) == 1 and assess_identity(candidate, direct[0]) != "none":
            return direct[0], "exact_external_id_and_identity"
    lat, lng = candidate.get("lat"), candidate.get("lng")
    if lat is not None and lng is not None:
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return None, "invalid_coordinates"
        # Approximately 110 m bounding box; indexed (lat,lng) narrows the
        # million-row Place table before exact name/address verification.
        nearby = list(Place.objects.filter(
            lat__gte=lat - .001, lat__lte=lat + .001,
            lng__gte=lng - .0013, lng__lte=lng + .0013,
        )[:101])
        if len(nearby) > 100:
            return None, "ambiguous"
        matches = [place for place in nearby if assess_identity(candidate, place) != "none"]
    else:
        name = str(candidate.get("name") or "").strip()
        address = str(candidate.get("address") or "").strip()
        if not name or not address:
            return None, "insufficient_identity"
        # Web candidates without coordinates require exact full fields.
        matches = [
            place for place in Place.objects.filter(
                Q(address__iexact=address) | Q(detail_location__iexact=address),
                name__iexact=name,
            )[:3] if assess_identity(candidate, place) != "none"
        ]
    if len(matches) == 1:
        return matches[0], "exact_identity"
    return None, "ambiguous" if matches else "no_match"
