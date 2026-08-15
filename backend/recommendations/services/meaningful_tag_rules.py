"""Evidence-only tag rules for attributes that place search APIs rarely expose."""

from dataclasses import dataclass


NEGATIVE_MARKERS = (
    "없음", "없다", "불가", "불가능", "미제공", "미보유", "해당없음",
    "아니오", "false", "none", "미운영",
)
EMPTY_MARKERS = ("", "-", "null", "미상", "정보없음", "확인필요")


@dataclass(frozen=True)
class MeaningfulTagRule:
    tag: str
    fields: tuple[str, ...]
    description: str
    confidence: int = 92


# Category names such as cafe, restaurant, toilet and library are deliberately
# absent. Every rule describes an operational, accessibility or facility fact.
MEANINGFUL_TAG_RULES = (
    MeaningfulTagRule("주차가능", (
        "parking", "parkingfood", "parkingculture", "parkinglodging",
        "parkingleports", "주차가능여부", "주차시설", "주차정보",
    ), "공식 원문에 주차 가능 또는 주차시설이 명시됨"),
    MeaningfulTagRule("장애인전용주차", (
        "장애인전용주차구역보유여부", "parking 장애인", "장애인주차장",
    ), "장애인 전용 주차구역이 명시됨", 96),
    MeaningfulTagRule("예약가능", (
        "reservation", "reservationfood", "reservationlodging",
        "예약가능여부", "예약안내",
    ), "예약 가능 여부가 공식 원문에 명시됨"),
    MeaningfulTagRule("포장가능", (
        "packing", "포장가능여부", "포장여부",
    ), "포장 가능 여부가 공식 원문에 명시됨"),
    MeaningfulTagRule("반려동물동반", (
        "chkpet", "petallowed", "acmpytypecd", "동반구분",
        "반려동물동반가능정보", "반려동물동반여부",
    ), "반려동물 동반 가능 조건이 공식 원문에 명시됨", 96),
    MeaningfulTagRule("휠체어접근", (
        "wheelchair", "휠체어", "장애인접근성", "주출입구접근로",
    ), "휠체어 또는 장애인 접근 정보가 명시됨", 96),
    MeaningfulTagRule("유모차접근", (
        "chkbabycarriage", "stroller", "유모차", "유모차대여",
    ), "유모차 접근 또는 대여 정보가 명시됨", 96),
    MeaningfulTagRule("유아시설", (
        "kidsfacility", "유아시설", "유아놀이방", "어린이시설",
    ), "유아·어린이 시설이 공식 원문에 명시됨", 95),
    MeaningfulTagRule("수유실", ("lactationroom", "수유실"),
                     "수유실 제공이 공식 원문에 명시됨", 97),
    MeaningfulTagRule("기저귀교환대", ("diaperchanging", "기저귀교환대", "기저귀교환대유무"),
                     "기저귀 교환대가 공식 원문에 명시됨", 97),
    MeaningfulTagRule("장애인화장실", (
        "disabledtoilet", "장애인용화장실", "장애인화장실",
    ), "장애인 화장실이 공식 원문에 명시됨", 97),
    MeaningfulTagRule("장애인시설", (
        "남성용-장애인용대변기수", "남성용-장애인용소변기수",
        "여성용-장애인용대변기수", "장애인용대변기수", "장애인용소변기수",
    ), "공식 원문에 장애인용 화장실 기구가 1개 이상 명시됨", 97),
    MeaningfulTagRule("무료이용", (
        "요금정보", "fee", "usefee", "이용요금", "입장료",
    ), "공식 이용요금 필드가 무료로 명시됨", 95),
    MeaningfulTagRule("무료와이파이", (
        "wifi", "무료wifi", "무료와이파이", "무선인터넷",
    ), "무료 무선인터넷 제공이 공식 원문에 명시됨", 95),
    MeaningfulTagRule("카드결제가능", (
        "chkcreditcard", "chkcreditcardfood", "creditcard",
        "신용카드가능여부", "카드결제", "결제방법",
    ), "카드 결제 가능 여부가 공식 원문에 명시됨"),
    MeaningfulTagRule("야외좌석", (
        "outdoorseating", "terrace", "야외좌석", "테라스좌석",
    ), "야외 좌석이 공식 원문에 명시됨"),
    MeaningfulTagRule("놀이시설", (
        "공원보유시설(유희시설)", "놀이시설", "유희시설",
    ), "공식 원문에 놀이·유희시설이 명시됨", 95),
    MeaningfulTagRule("운동시설", (
        "공원보유시설(운동시설)", "운동시설",
    ), "공식 원문에 운동시설이 명시됨", 95),
    MeaningfulTagRule("편의시설", (
        "공원보유시설(편익시설)", "편익시설", "편의시설",
    ), "공식 원문에 편의시설이 명시됨", 95),
    MeaningfulTagRule("야간운영", (
        "CHCK_MATTER_NIGHT_OPN_AT", "야간운영여부", "야간개방여부",
    ), "공식 원문에 야간 개방 여부가 Y로 명시됨", 96),
    MeaningfulTagRule("주말휴일운영", (
        "CHCK_MATTER_WKEND_HDAY_OPN_AT", "주말휴일개방여부",
    ), "공식 원문에 주말·휴일 개방 여부가 Y로 명시됨", 96),
    MeaningfulTagRule("냉방시설있음", (
        "COLR_HOLD_ARCNDTN", "냉방시설보유수", "에어컨보유수",
    ), "공식 원문에 냉방시설 보유 수가 1개 이상 명시됨", 97),
    MeaningfulTagRule("숙박가능", (
        "CHCK_MATTER_STAYNG_PSBL_AT", "숙박가능여부",
    ), "공식 원문에 숙박 가능 여부가 Y로 명시됨", 96),
)


def flatten_mapping(value, prefix=""):
    """Yield leaf fields from arbitrarily nested source JSON."""
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from flatten_mapping(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from flatten_mapping(child, f"{prefix}[{index}]")
    else:
        yield prefix, value


def normalize_field_name(value):
    return "".join(str(value or "").lower().split()).replace("_", "")


def meaningful_value(field, value, tag):
    text = str(value or "").strip().lower()
    compact = "".join(text.split())
    if compact in EMPTY_MARKERS or any(marker in compact for marker in NEGATIVE_MARKERS):
        return False
    if tag == "무료이용":
        return "무료" in compact or compact in {"0", "0원"}
    if tag == "장애인시설" and "장애인용" in field:
        try:
            return float(compact) > 0
        except ValueError:
            return False
    if tag == "카드결제가능" and field == normalize_field_name("결제방법"):
        return "카드" in compact
    if tag == "냉방시설있음":
        try:
            return float(compact) > 0
        except ValueError:
            return False
    if tag == "반려동물동반" and compact in {"n", "no", "0"}:
        return False
    if compact in {"n", "no", "0", "false"}:
        return False
    return bool(compact)


def extract_meaningful_tags(raw):
    leaves = list(flatten_mapping(raw or {}))
    matches = []
    for rule in MEANINGFUL_TAG_RULES:
        for path, value in leaves:
            field = normalize_field_name(path.rsplit(".", 1)[-1])
            matched = next(
                (name for name in rule.fields if normalize_field_name(name) == field),
                None,
            )
            if matched is None or not meaningful_value(field, value, rule.tag):
                continue
            matches.append({
                "tag": rule.tag,
                "field": path,
                "value": value,
                "description": rule.description,
                "confidence": rule.confidence,
            })
            break
    all_day = extract_24_hour_match(leaves)
    if all_day:
        matches.append(all_day)
    return matches


def extract_24_hour_match(leaves):
    """Return a direct all-day fact only when official fields explicitly support it."""
    values = {
        normalize_field_name(path.rsplit(".", 1)[-1]): str(value or "").strip()
        for path, value in leaves
    }
    for field_name in ("개방시간", "개방시간상세", "운영시간"):
        value = values.get(normalize_field_name(field_name), "")
        compact = "".join(value.lower().split())
        if any(marker in compact for marker in ("24시간", "24시개방", "상시개방")) or compact == "상시":
            return {
                "tag": "24시간운영",
                "field": field_name,
                "value": value,
                "description": "공식 원문에 24시간 또는 상시 개방이 명시됨",
                "confidence": 97,
            }

    days = "".join(values.get(normalize_field_name("운영요일"), "").split())
    required_days = ("평일", "토요일", "공휴일")
    if all(day in days for day in required_days):
        schedules = []
        for prefix in required_days:
            start = values.get(normalize_field_name(f"{prefix}운영시작시각"), "")
            end = values.get(normalize_field_name(f"{prefix}운영종료시각"), "")
            schedules.append((start, end))
        if all(start in {"00:00", "0:00"} and end in {"23:59", "24:00"} for start, end in schedules):
            return {
                "tag": "24시간운영",
                "field": "운영요일+요일별운영시각",
                "value": f"{days}; {schedules}",
                "description": "공식 운영요일과 요일별 시각이 전일 운영으로 명시됨",
                "confidence": 97,
            }
    weekday_start = values.get(normalize_field_name("WKDAY_OPER_BEGIN_TIME"), "")
    weekday_end = values.get(normalize_field_name("WKDAY_OPER_END_TIME"), "")
    weekend_start = values.get(normalize_field_name("WKEND_HDAY_OPER_BEGIN_TIME"), "")
    weekend_end = values.get(normalize_field_name("WKEND_HDAY_OPER_END_TIME"), "")
    weekend_enabled = values.get(normalize_field_name("CHCK_MATTER_WKEND_HDAY_OPN_AT"), "").lower()
    if (
        normalize_clock_text(weekday_start) == "0000"
        and normalize_clock_text(weekday_end) in {"2359", "2400"}
        and weekend_enabled in {"y", "yes", "true", "1"}
        and normalize_clock_text(weekend_start) == "0000"
        and normalize_clock_text(weekend_end) in {"2359", "2400"}
    ):
        return {
            "tag": "24시간운영",
            "field": "평일+주말휴일운영시각",
            "value": f"weekday={weekday_start}-{weekday_end}; weekend={weekend_start}-{weekend_end}",
            "description": "공식 평일·주말·휴일 운영시각이 모두 전일 운영으로 명시됨",
            "confidence": 97,
        }
    return None


def normalize_clock_text(value):
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits.zfill(4) if digits else ""
