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
    MeaningfulTagRule("기저귀교환대", ("diaperchanging", "기저귀교환대"),
                     "기저귀 교환대가 공식 원문에 명시됨", 97),
    MeaningfulTagRule("장애인화장실", (
        "disabledtoilet", "장애인용화장실", "장애인화장실",
    ), "장애인 화장실이 공식 원문에 명시됨", 97),
    MeaningfulTagRule("무료이용", (
        "요금정보", "fee", "usefee", "이용요금", "입장료",
    ), "공식 이용요금 필드가 무료로 명시됨", 95),
    MeaningfulTagRule("무료와이파이", (
        "wifi", "무료wifi", "무료와이파이", "무선인터넷",
    ), "무료 무선인터넷 제공이 공식 원문에 명시됨", 95),
    MeaningfulTagRule("카드결제가능", (
        "chkcreditcard", "chkcreditcardfood", "creditcard",
        "신용카드가능여부", "카드결제",
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
    return matches
