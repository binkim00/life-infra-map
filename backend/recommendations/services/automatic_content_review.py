"""Content-only automatic acceptance. Never manufactures a fresh observation."""
import hashlib
import re
from urllib.parse import urlsplit, parse_qs

from django.db import transaction
from django.utils import timezone
from recommendations.models import EvidenceReview, PlaceTagEvidence
from .naver_tag_evidence_provider import identity_assessment, polarity_assessment
from .tag_source_policy import WEB_EVIDENCE_SOURCES

POLICY_VERSION = "content-v3-20260910"

BRANCH_SENSITIVE_BRANDS = (
    "스타벅스", "투썸플레이스", "메가mgc커피", "메가커피", "컴포즈커피",
    "이디야", "빽다방", "파스쿠찌", "할리스", "엔제리너스", "커피빈",
    "카페베네", "더벤티", "매머드커피", "폴바셋", "탐앤탐스", "공차",
    "블루샥", "롯데리아", "맥도날드", "버거킹", "맘스터치", "서브웨이",
    "kfc", "설빙", "텐퍼센트", "채선당", "배스킨라빈스", "파리바게뜨",
)


def compact(value):
    return re.sub(r"[^a-z0-9가-힣]", "", str(value).lower())


def roads(text):
    return {compact(a) + b for a, b in re.findall(r"([가-힣0-9]+(?:대로|로|길))\s*(\d+(?:-\d+)?)", text)}


def duplicate_key(row):
    url = urlsplit(row.source_reference)
    query = parse_qs(url.query)
    reference = row.source_reference.rstrip("/")
    if url.hostname in ("blog.naver.com", "m.blog.naver.com"):
        parts = url.path.strip("/").split("/")
        if query.get("blogId") and query.get("logNo"):
            reference = "naver:" + query["blogId"][0].lower() + ":" + query["logNo"][0]
        elif len(parts) == 2 and parts[1].isdigit():
            reference = "naver:" + parts[0].lower() + ":" + parts[1]
    return (row.place_id, row.tag_id, row.polarity, reference, compact(row.evidence))


def full_name_mentioned(row, text=None):
    name = compact(row.place.name)
    return len(name) >= 4 and name in compact(text if text is not None else row.evidence)


def branch_sensitive_place(place):
    raw = place.raw if isinstance(place.raw, dict) else {}
    branch = next((raw.get(key) for key in (
        "지점명", "branch_name", "brchNm", "branch",
    ) if str(raw.get(key) or "").strip()), "")
    name = compact(place.name)
    return bool(branch) or any(compact(brand) in name for brand in BRANCH_SENSITIVE_BRANDS)


def explicit_opposite_statement(row, text):
    if row.polarity != "positive":
        return False
    body = compact(text)
    tag = row.tag.name
    if tag == "데이트좋음":
        return bool(re.search(r"데이트.{0,12}(?:아님|아니|불가|어렵)", body))
    if tag in ("작업하기좋음", "노트북작업"):
        return bool(re.search(r"(?:노트북|태블릿|랩탑).{0,20}(?:사용하지말|금지|불가)", body))
    if tag == "콘센트있음":
        return bool(re.search(r"콘센트.{0,12}(?:없|불가|금지)", body))
    if tag == "주차가능":
        return bool(re.search(r"주차.{0,12}(?:불가|안됨|없)", body))
    if tag in ("혼밥좋음", "혼자이용좋음"):
        return bool(re.search(r"(?:혼밥|혼자이용).{0,12}(?:불가|금지|어렵)", body))
    if tag == "조용함":
        return bool(re.search(r"(?:조용하지않|조용.{0,4}아님|조용한편은아니)", body))
    return False


def multiple_place_context_decision(row):
    name = compact(row.place.name)
    quote = compact(row.evidence)
    if len(name) < 4 or name not in quote:
        return "hold"
    start = 0
    opposite_found = False
    while True:
        position = quote.find(name, start)
        if position < 0:
            return "reject" if opposite_found else "hold"
        window = quote[max(0, position - 160):position + len(name) + 160]
        assessed = polarity_assessment(
            row.tag.name, window, category=row.place.category,
        )["polarity"]
        if assessed == row.polarity:
            return "approve"
        if assessed in ("positive", "negative"):
            opposite_found = True
        start = position + len(name)


def assess_content(row):
    """No expiration, exact-title, or network-access requirement."""
    if row.source not in WEB_EVIDENCE_SOURCES:
        return "hold", "unsupported_source"
    prose = row.evidence or ""
    title = (row.context or {}).get("source_title", "")
    text = title + " " + prose
    name = compact(row.place.name)
    body = compact(prose)
    if len(body) < 8 or not row.source_reference.startswith(("https://", "http://")):
        return "reject", "insufficient_content_or_source"
    address_roads, quote_roads = roads(row.place.address), roads(prose)
    same_road = bool(address_roads & quote_roads)
    if address_roads and quote_roads and not same_road:
        return "hold", "different_address_needs_branch_or_move_check"
    identity = identity_assessment(row.place, text, title=title)
    if identity.get("signals", {}).get("explicit_region_mismatch"):
        return "reject", "region_mismatch"
    # A distinctive full name in the quote is sufficient even if omitted in
    # the title. For a branch-name omission require the exact road number.
    name_terms = [compact(x) for x in re.findall(r"[a-zA-Z0-9가-힣]+", row.place.name) if len(compact(x)) >= 2]
    name_matches = (len(name) >= 4 and name in compact(text)) or (same_road and any(x in compact(text) for x in name_terms))
    if not (name_matches or identity.get("matched")):
        if branch_sensitive_place(row.place) and not full_name_mentioned(row, text):
            return "hold", "place_identity_uncertain_for_branch"
    if re.search(r"top\s*\d|best\s*\d|총정리|리스트|모음|\d+\s*곳", title, re.I):
        multiple_decision = multiple_place_context_decision(row)
        if multiple_decision != "approve":
            return multiple_decision, "multiple_place_scope"
    # Explicit city conflict is not excused by a matching chain name.
    cities = "서울 부산 대구 인천 광주 대전 울산 세종 창원 양산 김해 진주 수원 성남 고양 용인 화성 전주 군산 익산 청주 천안 안산 제주 서귀포".split()
    expected = {x for x in cities if x in row.place.address}
    title_cities = {x for x in cities if re.search(r"(?:^|\s|[\[|(])" + x + r"(?:시|\s|맛집|카페|[|/\]])", title)}
    if expected and title_cities and not expected.intersection(title_cities):
        return "reject", "title_city_mismatch"
    mentioned = {x for x in cities if re.search(r"(?:^|\s|[\[|(])" + x + r"(?:시|\s|맛집|카페|[|/\]])", text)}
    if expected and mentioned and not expected.intersection(mentioned):
        return "reject", "city_mismatch"
    district_pattern = r"([가-힣0-9]{2,}(?:동|읍|면))(?=맛집|카페|\s|[)\],]|$)"
    expected_districts = set(re.findall(district_pattern, row.place.address))
    title_districts = set(re.findall(district_pattern, title))
    if explicit_opposite_statement(row, text):
        return "reject", "explicit_opposite_statement"
    return "approve", "relaxed_place_and_content_supported"


@transaction.atomic
def auto_review_content(row, *, decision=None, reason=None, run_key="new_collection"):
    """Respect manual decisions; an automatic decision is rechecked on update."""
    row = PlaceTagEvidence.objects.select_for_update().select_related("place", "tag").get(pk=row.pk)
    review = EvidenceReview.objects.filter(evidence=row).first()
    if review and (review.reviewer_id or not review.history or review.history[-1].get("mode") != "automatic_content"):
        return "preserved_manual"
    if decision is None:
        decision, reason = assess_content(row)
        if decision == "approve":
            peers = PlaceTagEvidence.objects.filter(place_id=row.place_id, tag_id=row.tag_id, polarity=row.polarity, source__in=WEB_EVIDENCE_SOURCES, id__lt=row.id)
            if any(duplicate_key(peer) == duplicate_key(row) for peer in peers):
                decision, reason = "duplicate", "duplicate_original_preserved"
    status = {
        "approve": "approved",
        "limited": "approved_limited",
        "hold": "pending",
        "duplicate": "rejected",
        "reject": "rejected",
    }[decision]
    digest = hashlib.sha256(row.evidence.encode()).hexdigest()
    entry = {"mode": "automatic_content", "policy": POLICY_VERSION, "status": status, "reason": reason,
             "quote_hash": digest, "run_key": run_key, "at": timezone.now().isoformat()}
    if review and review.status == status and review.history[-1].get("quote_hash") == digest and review.history[-1].get("policy") == POLICY_VERSION and review.history[-1].get("reason") == reason:
        return "unchanged"
    if review is None:
        review = EvidenceReview(evidence=row)
    review.status = status
    review.note = f"자동 내용 검토 [{POLICY_VERSION}]: {reason}. 저장 문장 기준이며 현장 확인/최신 원문 재검증이 아닙니다. 원본·관측일·만료일 보존."
    review.history = [*review.history, entry]
    review.save()
    # Deliberately no admin_review evidence: automatic content acceptance
    # must never impersonate human/current verification.
    return status
