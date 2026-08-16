import re
import unicodedata
from difflib import SequenceMatcher

from recommendations.services.map_search import calculate_distance_m


CAFE_ALLOWED_TYPES = {"카페"}
RESTAURANT_EXCLUDED_TYPES = {
    "요리 주점",
    "일반 유흥 주점",
    "생맥주 전문",
    "무도 유흥 주점",
    "빵/도넛",
    "떡/한과",
    "아이스크림/빙수",
    "구내식당",
    "편의점",
}
NON_PLACE_TYPES = {
    "기타 오락장",
    "PC방",
    "셀프 빨래방",
    "당구장",
    "채소/과일 소매업",
    "수산물 소매업",
    "건강보조식품 소매업",
    "화장품 소매업",
    "애완동물/애완용품 소매업",
}
REGION_ALIASES = {
    "서울특별시": ("서울특별시", "서울"),
    "부산광역시": ("부산광역시", "부산"),
}


def normalize_name(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"\(\s*주\s*\)|㈜|주식회사|유한회사", "", text)
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def normalize_address(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"\(.*?\)", " ", text)
    for canonical, aliases in REGION_ALIASES.items():
        for alias in aliases:
            if text.startswith(alias.lower()):
                text = canonical[:2].lower() + text[len(alias):]
                break
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def is_service_category(record):
    business_type = str(record.business_type or "").strip()
    normalized_name = normalize_name(record.name)
    if record.category == "cafe":
        return business_type in CAFE_ALLOWED_TYPES
    if record.category == "restaurant":
        return bool(
            business_type
            and business_type not in RESTAURANT_EXCLUDED_TYPES
            and business_type not in NON_PLACE_TYPES
            # A restaurant-classified row with an explicit cafe identity is a
            # source classification conflict. Do not guess a replacement
            # category from the trade name alone.
            and not any(term in normalized_name for term in ("카페", "커피", "다방", "스터디카페"))
        )
    return False


def valid_coordinates(record):
    try:
        lng = float(record.source_x)
        lat = float(record.source_y)
    except (TypeError, ValueError):
        return None
    if not (123.0 <= lng <= 132.0 and 32.0 <= lat <= 39.5):
        return None
    return round(lat, 7), round(lng, 7)


def exact_identity_key(name, address):
    normalized_name = normalize_name(name)
    normalized_address = normalize_address(address)
    if not normalized_name or not normalized_address:
        return None
    return normalized_name, normalized_address


def possible_duplicate(source_record, place, *, source_coordinates):
    """Classify only conservative cross-source duplicate signals.

    Exact normalized names plus either an exact address or <=30 m are safe to
    link. Similar-but-not-exact nearby rows remain ambiguous and are never
    merged automatically.
    """
    source_name = normalize_name(source_record.name)
    place_name = normalize_name(place.name)
    if not source_name or not place_name:
        return "none"
    distance = calculate_distance_m(
        source_coordinates[0], source_coordinates[1], place.lat, place.lng
    )
    source_addresses = {
        normalize_address(source_record.road_address),
        normalize_address(source_record.address),
    } - {""}
    place_addresses = {
        normalize_address(place.address),
        normalize_address(place.detail_location),
    } - {""}
    exact_address = bool(source_addresses & place_addresses)
    if source_name == place_name and (exact_address or distance <= 30):
        return "confirmed"
    similarity = SequenceMatcher(None, source_name, place_name).ratio()
    if (exact_address and similarity >= 0.72) or (distance <= 30 and similarity >= 0.78):
        return "ambiguous"
    return "none"
