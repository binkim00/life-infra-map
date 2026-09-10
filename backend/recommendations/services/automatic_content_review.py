"""Content-only automatic acceptance. Never manufactures a fresh observation."""
import hashlib
import re
from urllib.parse import urlsplit, parse_qs

from django.db import transaction
from django.utils import timezone
from recommendations.models import EvidenceReview, PlaceTagEvidence
from .naver_tag_evidence_provider import identity_assessment, polarity_assessment
from .tag_source_policy import WEB_EVIDENCE_SOURCES

POLICY_VERSION = "content-v2-20260910"


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


def assess_content(row):
    """No expiration, exact-title, or network-access requirement."""
    if row.source not in WEB_EVIDENCE_SOURCES:
        return "hold", "unsupported_source"
    prose = (row.evidence or "").split("#", 1)[0]
    title = (row.context or {}).get("source_title", "")
    text = title + " " + prose
    name = compact(row.place.name)
    body = compact(prose)
    if len(body) < 8 or not row.source_reference.startswith(("https://", "http://")):
        return "hold", "insufficient_content_or_source"
    address_roads, quote_roads = roads(row.place.address), roads(prose)
    same_road = bool(address_roads & quote_roads)
    if address_roads and quote_roads and not same_road:
        return "hold", "different_address_needs_branch_or_move_check"
    identity = identity_assessment(row.place, text, title=title)
    if identity.get("signals", {}).get("explicit_region_mismatch"):
        return "hold", "region_mismatch"
    # A distinctive full name in the quote is sufficient even if omitted in
    # the title. For a branch-name omission require the exact road number.
    name_terms = [compact(x) for x in re.findall(r"[a-zA-Z0-9가-힣]+", row.place.name) if len(compact(x)) >= 2]
    name_matches = (len(name) >= 4 and name in compact(text)) or (same_road and any(x in compact(text) for x in name_terms))
    if not (name_matches or identity.get("matched")):
        return "hold", "place_identity_uncertain"
    if re.search(r"top\s*\d|best\s*\d|총정리|리스트|모음|\d+\s*곳", title, re.I) and not (same_road and len(quote_roads) == 1 and name in body):
        return "hold", "multiple_place_scope"
    if row.place.category in ("cafe", "restaurant") and re.search(r"호텔|모텔|펜션|리조트", row.place.name) and not re.search(r"카페|식당|레스토랑|라운지|뷔페", row.place.name):
        return "hold", "lodging_not_dining_scope"
    # Explicit city conflict is not excused by a matching chain name.
    cities = "서울 부산 대구 인천 광주 대전 울산 세종 창원 양산 김해 진주 수원 성남 고양 용인 화성 전주 군산 익산 청주 천안 안산 제주 서귀포".split()
    expected = {x for x in cities if x in row.place.address}
    title_cities = {x for x in cities if re.search(r"(?:^|\s|[\[|(])" + x + r"(?:시|\s|맛집|카페|[|/\]])", title)}
    if expected and title_cities and not expected.intersection(title_cities):
        return "hold", "title_city_mismatch"
    mentioned = {x for x in cities if re.search(r"(?:^|\s|[\[|(])" + x + r"(?:시|\s|맛집|카페|[|/\]])", text)}
    if expected and mentioned and not expected.intersection(mentioned):
        return "hold", "city_mismatch"
    district_pattern = r"([가-힣0-9]{2,}(?:동|읍|면))(?=맛집|카페|\s|[)\],]|$)"
    expected_districts = set(re.findall(district_pattern, row.place.address))
    title_districts = set(re.findall(district_pattern, title))
    if expected_districts and title_districts and not expected_districts.intersection(title_districts) and not same_road:
        return "hold", "neighborhood_mismatch"
    tag = row.tag.name
    if tag in ("조용함", "소음큼"):
        if not re.search(r"조용|한적|차분(?:한|하|해|히|함)|소음|시끄|시끌|북적|혼잡", prose):
            return "hold", "ambience_is_not_noise_evidence"
        if re.search(r"조용.{0,12}(?:해야|이용해야)|피해가안가게", body):
            return "hold", "etiquette_not_observation"
        if row.place.category not in ("library", "cafe", "restaurant") and re.search(r"도서관|개별룸", title):
            return "hold", "subfacility_not_whole_place"
    if tag == "관리잘됨" and re.search(r"불법투기|단속|상습지역", body):
        return "hold", "enforcement_not_cleanliness"
    if tag == "무료와이파이" and row.polarity == "positive" and not re.search(r"(?:무료|공공|free).{0,10}(?:와이파이|wi.?fi)|(?:와이파이|wi.?fi).{0,10}(?:무료|free)", prose, re.I):
        return "hold", "wifi_available_does_not_prove_free"
    if tag == "노트북작업" and not re.search(r"노트북|랩탑|laptop", prose, re.I):
        return "hold", "study_does_not_prove_laptop"
    if tag in ("시간제한있음", "장기체류좋음") and re.search(r"시간(?:이)?제한.{0,8}없", body) and (tag, row.polarity) in (("시간제한있음", "positive"), ("장기체류좋음", "negative")):
        return "hold", "negation_misinterpretation"
    if tag in ("혼밥좋음", "혼자이용좋음") and re.search(r"집에서.{0,10}혼밥|혼밥.{0,8}(?:불가|어렵|하고싶|하러갈)", body):
        return "hold", "home_intent_or_negation"
    assessment = polarity_assessment(tag, prose, category=row.place.category)
    if assessment["polarity"] != row.polarity or row.polarity not in ("positive", "negative"):
        return "hold", "tag_polarity_not_supported"
    return "approve", "place_and_content_supported"


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
