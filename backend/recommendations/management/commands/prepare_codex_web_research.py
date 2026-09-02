import csv
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagCollectionJob, PlaceTagEvidence, TagEnrichmentRequest
from recommendations.services.public_page_tag_evidence import fetch_public_page
from recommendations.services.restaurant_collection_quality import restaurant_collection_quality
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES
from recommendations.services.web_tag_evidence_provider import CATEGORY_TAGS
from recommendations.services.place_evidence_completeness import target_tags_for_gaps


MAX_TARGET_TAGS = 8
MAX_SOURCE_HINTS = 5
PREFLIGHT_POOL_MULTIPLIER = 2
CODEX_UNREADABLE_HOSTS = ("blog.naver.com", "m.blog.naver.com")

# Tags whose supporting language is commonly present in public reviews and
# venue introductions come first. Facility facts remain useful candidates, but
# a run should not spend its only attempt on a very specific, rarely written
# detail when another missing recommendation dimension is researchable.
RESEARCHABILITY_PRIORITY = (
    "분위기좋음", "데이트좋음", "혼자이용좋음", "혼밥좋음", "대화하기좋음",
    "전망좋음", "사진찍기좋음", "디저트특화", "커피맛좋음", "가성비좋음",
    "대표메뉴뚜렷함", "여럿이먹기좋은메뉴", "메뉴선택폭넓음", "야외좌석",
    "반려동물동반", "단체석있음", "개별룸있음", "넓은테이블", "편한좌석",
    "자연채광좋음", "조용함", "웨이팅많음", "웨이팅적음", "예약필수",
    "시간제한있음", "좌석없음", "작업하기좋음", "노트북작업", "콘센트있음",
    "장기체류좋음", "좌석간격넓음", "유아의자있음", "유모차접근",
    "아이메뉴있음", "무단차접근", "엘리베이터있음", "주차어려움",
    "계단접근만가능", "테이크아웃전문", "와이파이있음", "무료와이파이",
)
RESEARCHABILITY_INDEX = {tag: index for index, tag in enumerate(RESEARCHABILITY_PRIORITY)}

# Canonical tags are compact database labels, while public reviews usually use
# ordinary Korean phrases.  Passing a small vocabulary with the seed lets the
# researcher search for the meaning instead of the exact label only.
TAG_SEARCH_TERMS = {
    "분위기좋음": ("분위기가 좋", "분위기 있는", "감성적인"),
    "데이트좋음": ("데이트", "커플", "둘이 가기"),
    "혼자이용좋음": ("혼자", "혼카페", "1인 이용"),
    "혼밥좋음": ("혼밥", "혼자 먹", "1인 식사"),
    "대화하기좋음": ("대화하기 좋", "이야기하기 좋", "모임하기 좋"),
    "사진찍기좋음": ("사진 찍기 좋", "포토존", "사진이 잘 나"),
    "커피맛좋음": ("커피가 맛", "원두", "커피 맛집"),
    "디저트특화": ("디저트", "베이커리", "케이크"),
    "대표메뉴뚜렷함": ("대표 메뉴", "시그니처", "인기 메뉴"),
    "가성비좋음": ("가성비", "가격이 저렴", "가격 대비"),
    "메뉴선택폭넓음": ("메뉴가 다양", "메뉴 종류", "선택지가 많"),
    "여럿이먹기좋은메뉴": ("여럿이", "함께 먹", "나눠 먹"),
    "조용함": ("조용", "한적", "차분"),
    "노트북작업": ("노트북", "랩탑", "카공"),
    "작업하기좋음": ("작업하기 좋", "공부하기 좋", "업무 보기 좋"),
    "장기체류좋음": ("오래 머물", "장시간", "오래 있기"),
    "콘센트있음": ("콘센트", "전원", "충전"),
    "와이파이있음": ("와이파이", "wifi", "무선 인터넷"),
    "무료와이파이": ("무료 와이파이", "와이파이 비밀번호", "wifi 무료"),
    "단체석있음": ("단체석", "단체 좌석", "단체 이용"),
    "개별룸있음": ("개별 룸", "룸 있음", "프라이빗 룸"),
    "넓은테이블": ("테이블이 넓", "큰 테이블", "넓은 탁자"),
    "좌석간격넓음": ("좌석 간격", "테이블 간격", "자리 간격"),
    "편한좌석": ("좌석이 편", "의자가 편", "소파 좌석"),
    "야외좌석": ("야외 좌석", "테라스", "루프탑"),
    "자연채광좋음": ("채광", "햇살", "통창"),
    "반려동물동반": ("반려동물 동반", "애견 동반", "강아지 동반"),
    "예약가능": ("예약 가능", "예약할 수", "예약하고"),
    "예약필수": ("예약 필수", "예약해야", "사전 예약"),
    "웨이팅많음": ("웨이팅", "대기 줄", "기다려야"),
    "웨이팅적음": ("웨이팅 없", "대기 없이", "바로 입장"),
    "시간제한있음": ("이용 시간 제한", "시간 제한", "2시간 이용"),
    "테이크아웃전문": ("테이크아웃 전문", "포장 전문", "좌석 없는"),
    "유아의자있음": ("유아 의자", "아기 의자", "하이체어"),
    "아이메뉴있음": ("아이 메뉴", "어린이 메뉴", "키즈 메뉴"),
    "유모차접근": ("유모차", "유모차 입장", "유모차 접근"),
    "무단차접근": ("휠체어", "단차 없", "배리어프리"),
    "엘리베이터있음": ("엘리베이터", "승강기"),
    "주차어려움": ("주차 어려", "주차 공간 없", "주차 불가"),
    "계단접근만가능": ("계단으로", "계단만", "엘리베이터 없"),
    "좌석없음": ("좌석 없", "앉을 자리 없", "스탠딩"),
    "혼잡함": ("붐비", "혼잡", "사람이 많"),
    "소음큼": ("시끄럽", "소음", "북적"),
}


def research_priority(place, launch_demands, *, quality_score=0):
    """Prefer source-ready launch gaps, then source-ready coverage, then cold launch gaps."""
    demand_score = sum(launch_demands.get(place.id, {}).values())
    identity_ready = bool(place.identity_success)
    tier = 0 if identity_ready and demand_score else 1 if identity_ready else 2
    return (
        tier,
        -demand_score,
        -quality_score,
        -int(place.evidence_success),
        -int(place.no_tag),
        place.name,
    )


class Command(BaseCommand):
    help = "Prepare a Busan-only Codex web research seed file without calling providers."

    def add_arguments(self, parser):
        parser.add_argument("--cafe", type=int, default=50)
        parser.add_argument("--restaurant", type=int, default=50)
        parser.add_argument(
            "--corroboration", type=int, default=0,
            help="Total places reserved for adding a second independent web source.",
        )
        parser.add_argument("--output", default="tmp/codex_web_evidence_busan_pilot.json")
        parser.add_argument("--exclude-place-ids", default="")
        parser.add_argument("--preflight-source-hints", action="store_true")

    def handle(self, *args, **options):
        candidates = []
        allocation = Counter()
        requested_limits = {}
        excluded = {
            int(value) for value in str(options["exclude_place_ids"] or "").split(",")
            if value.strip().isdigit()
        }
        for category in ("cafe", "restaurant"):
            requested_limits[category] = max(0, int(options[category]))
        requested_total = sum(requested_limits.values())
        corroboration_total = int(options["corroboration"] or 0)
        if corroboration_total < 0 or corroboration_total > requested_total:
            raise CommandError("--corroboration must be between 0 and the total place limit")
        corroboration_quotas = allocate_corroboration_quotas(
            requested_limits, corroboration_total,
        )
        mixed_selection = corroboration_total > 0
        for category in ("cafe", "restaurant"):
            limit = max(0, int(options[category]))
            pool_limit = (
                limit
                if mixed_selection
                else limit * PREFLIGHT_POOL_MULTIPLIER if options["preflight_source_hints"] else limit
            )
            rows = select_places(
                category,
                pool_limit,
                allocation,
                exclude_place_ids=excluded,
                corroboration_limit=(corroboration_quotas[category] if mixed_selection else None),
            )
            if len(rows) < limit:
                raise CommandError("Only {} eligible {} places found".format(len(rows), category))
            candidates.extend(rows)
        preflight = {"checked": 0, "reachable": 0, "rejected": 0}
        if options["preflight_source_hints"]:
            preflight = preflight_source_hints(candidates)
        selected = []
        for category in ("cafe", "restaurant"):
            category_rows = [row for row in candidates if row["place"].category == category]
            selected.extend(
                category_rows
                if mixed_selection
                else prefer_source_ready(category_rows, requested_limits[category])
            )
        payload = {
            "region": "부산",
            "generated_at": timezone.now().isoformat(),
            "paid_api_calls": 0,
            "results": [seed_row(item) for item in selected],
        }
        path = Path(options["output"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        csv_path = path.with_suffix(".csv")
        fields = list(payload["results"][0]) if payload["results"] else []
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(payload["results"])
        self.stdout.write(json.dumps({
            "places": len(selected),
            "candidate_pool": len(candidates),
            "categories": dict(Counter(row["place"].category for row in selected)),
            "target_tags": dict(Counter(row["tag"] for row in selected)),
            "launch_priority_places": sum(bool(row.get("launch_demand")) for row in selected),
            "research_mix": dict(Counter(row.get("research_track") for row in selected)),
            "requested_corroboration": corroboration_total,
            "corroboration_quotas": corroboration_quotas,
            "source_hint_preflight": preflight,
            "json": str(path), "csv": str(csv_path),
        }, ensure_ascii=False))


def prefer_source_ready(rows, limit):
    """Prefer reachable pages; within each tier, keep launch gaps first."""
    def tier(row):
        has_source = bool(row.get("source_hints"))
        has_demand = bool(row.get("launch_demand"))
        if has_source and has_demand:
            return 0
        if has_source:
            return 1
        if has_demand:
            return 2
        return 3

    return sorted(rows, key=tier)[:limit]


def select_places(
    category, limit, allocation, *, exclude_place_ids=None, corroboration_limit=None,
):
    tags = CATEGORY_TAGS[category]
    exclude_place_ids = exclude_place_ids or set()
    launch_demands = launch_demand_context(category)
    launch_place_ids = set(launch_demands)
    identity_job = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider="naver_search", status="completed",
        stats__diagnostics__identity_matches__gt=0,
    )
    no_tag_job = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider="naver_search", status="completed",
        stats__miss_reason="NO_TAG_EXPRESSION",
    )
    evidence_job = PlaceTagCollectionJob.objects.filter(
        place_id=OuterRef("pk"), provider="naver_search", status="completed",
        stats__evidences__gt=0,
    )
    places = list(Place.objects.filter(
        Q(address__startswith="부산") | Q(detail_location__startswith="부산"), category=category,
    ).exclude(id__in=exclude_place_ids).annotate(
        identity_success=Exists(identity_job), no_tag=Exists(no_tag_job),
        evidence_success=Exists(evidence_job),
    ).filter(Q(identity_success=True) | Q(id__in=launch_place_ids)).order_by(
        "-no_tag", "-evidence_success", "name",
    )[:5000])
    if category == "restaurant":
        scored = []
        for place in places:
            quality = restaurant_collection_quality(
                place, successful_jobs=int(place.evidence_success)
            )
            if quality["score"] < 8 or any(
                flag in quality["flags"]
                for flag in ("institutional_food_service", "contract_food_operator", "institutional_context")
            ):
                continue
            scored.append((quality["score"], place))
        places = [
            place for _score, place in sorted(
                scored,
                key=lambda item: research_priority(
                    item[1], launch_demands, quality_score=item[0],
                ),
            )
        ]
    else:
        places.sort(key=lambda place: research_priority(place, launch_demands))
    active = defaultdict(list)
    for row in PlaceTagEvidence.objects.filter(
        place_id__in=[place.id for place in places],
        tag__name__in=tags,
        polarity__in=("positive", "negative"),
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).values(
        "place_id", "tag__name", "polarity", "source", "source_reference",
    ):
        active[row["place_id"]].append({**row, "tag_name": row["tag__name"]})
    selected = []
    corroboration_candidates = []
    discovery_candidates = []
    seen_names = set()
    for place in places:
        normalized_name = "".join(str(place.name or "").lower().split())
        if len(normalized_name) < 3 or normalized_name in seen_names:
            continue
        missing = [
            tag for tag in target_tags_for_gaps(category, active[place.id], limit=len(tags))
            if tag in tags
        ]
        corroboration = corroboration_tags(active[place.id])
        missing = list(dict.fromkeys([*corroboration, *missing]))
        if not missing:
            continue
        ordered_missing = order_missing_tags(
            missing,
            category=category,
            demand=launch_demands.get(place.id, {}),
            allocation=allocation,
            category_tags=tags,
            corroboration=corroboration,
        )
        tag = ordered_missing[0]
        allocation[(category, tag)] += 1
        seen_names.add(normalized_name)
        candidate = {
            "place": place,
            "tag": tag,
            "target_tags": [tag] + [value for value in ordered_missing if value != tag][:MAX_TARGET_TAGS - 1],
            "active_tags": sorted({row["tag_name"] for row in active[place.id]}),
            "source_hints": [],
            "launch_demand": launch_demands.get(place.id, {}),
            "corroboration_tags": corroboration,
            "research_track": "corroboration" if corroboration else "discovery",
        }
        if corroboration_limit is None:
            selected.append(candidate)
            if len(selected) >= limit:
                break
            continue
        bucket = corroboration_candidates if corroboration else discovery_candidates
        if len(bucket) < limit:
            bucket.append(candidate)
        discovery_limit = max(0, limit - corroboration_limit)
        if (
            len(corroboration_candidates) >= corroboration_limit
            and len(discovery_candidates) >= discovery_limit
        ):
            break
    if corroboration_limit is not None:
        selected = mixed_research_selection(
            corroboration_candidates,
            discovery_candidates,
            limit=limit,
            corroboration_limit=corroboration_limit,
        )
    source_hints = source_hints_for_places([row["place"].id for row in selected])
    for row in selected:
        row["source_hints"] = source_hints.get(row["place"].id, [])
    return selected


def allocate_corroboration_quotas(requested_limits, corroboration_total):
    """Distribute a global corroboration quota proportionally by category."""
    requested_total = sum(max(0, int(value)) for value in requested_limits.values())
    if not requested_total or corroboration_total <= 0:
        return {category: 0 for category in requested_limits}
    exact = {
        category: corroboration_total * max(0, int(limit)) / requested_total
        for category, limit in requested_limits.items()
    }
    quotas = {category: int(value) for category, value in exact.items()}
    remainder = corroboration_total - sum(quotas.values())
    ranked = sorted(
        requested_limits,
        key=lambda category: (-(exact[category] - quotas[category]), category),
    )
    for category in ranked[:remainder]:
        quotas[category] += 1
    return quotas


def mixed_research_selection(corroboration, discovery, *, limit, corroboration_limit):
    """Honor the requested mix and fill a shortage from the other track."""
    selected = [
        *corroboration[:corroboration_limit],
        *discovery[:max(0, limit - corroboration_limit)],
    ]
    selected_ids = {id(row) for row in selected}
    for row in [*corroboration, *discovery]:
        if len(selected) >= limit:
            break
        if id(row) not in selected_ids:
            selected.append(row)
            selected_ids.add(id(row))
    return selected


def launch_demand_context(category):
    location = Q(place__address__startswith="부산") | Q(place__detail_location__startswith="부산")
    requests = TagEnrichmentRequest.objects.filter(
        location, place__category=category, status="queued",
    ).values("place_id", "tag_name", "priority", "demand_count", "context")
    demands = defaultdict(dict)
    for request in requests:
        context = request.get("context") or {}
        launch = context.get("launch_quality")
        retry_candidate = context.get("codex_candidate_research")
        if request["tag_name"] not in CATEGORY_TAGS.get(category, ()):
            continue
        if isinstance(launch, dict):
            score = int(request.get("priority") or 0) + int(request.get("demand_count") or 0)
        elif isinstance(retry_candidate, dict):
            score = int(request.get("priority") or 0) + 10
        else:
            continue
        demands[request["place_id"]][request["tag_name"]] = score
    return demands


def preflight_source_hints(selected, *, fetcher=fetch_public_page, max_attempts_per_place=2):
    """Keep only source hints that the production page fetcher can read."""
    candidates = []
    for row in selected:
        for hint in (row.get("source_hints") or [])[:max_attempts_per_place]:
            candidates.append((row, hint))
    if not candidates:
        return {"checked": 0, "reachable": 0, "rejected": 0}
    outcomes = {}
    with ThreadPoolExecutor(max_workers=min(10, len(candidates))) as executor:
        futures = {executor.submit(fetcher, hint["url"]): (row, hint) for row, hint in candidates}
        for future in as_completed(futures):
            row, hint = futures[future]
            try:
                page = future.result()
            except Exception:
                page = {"ok": False}
            outcomes[(row["place"].id, hint["url"])] = page
    reachable = 0
    for row in selected:
        verified = []
        for hint in (row.get("source_hints") or [])[:max_attempts_per_place]:
            page = outcomes.get((row["place"].id, hint["url"])) or {}
            if not page.get("ok"):
                continue
            verified.append({
                **hint,
                "url": page.get("url") or hint["url"],
                "title": page.get("title") or hint.get("title") or "",
                "preflight_verified": True,
            })
            reachable += 1
        row["source_hints"] = verified
    return {
        "checked": len(candidates),
        "reachable": reachable,
        "rejected": len(candidates) - reachable,
    }


def source_hints_for_places(place_ids):
    hints = defaultdict(list)
    seen = defaultdict(set)
    evidences = PlaceTagEvidence.objects.filter(
        place_id__in=place_ids,
        source__in=WEB_EVIDENCE_SOURCES,
    ).exclude(source_reference="").order_by("-observed_at", "-id").values(
        "place_id", "source_reference", "evidence", "context",
    )
    for evidence in evidences:
        place_id = evidence["place_id"]
        url = str(evidence.get("source_reference") or "").strip()
        if len(hints[place_id]) >= MAX_SOURCE_HINTS or url in seen[place_id]:
            continue
        if not url.startswith(("http://", "https://")):
            continue
        if urlparse(url).hostname in CODEX_UNREADABLE_HOSTS:
            continue
        seen[place_id].add(url)
        context = evidence.get("context") or {}
        hints[place_id].append({
            "url": url,
            "title": str(context.get("source_title") or "")[:180],
            "description": str(evidence.get("evidence") or "")[:500],
            "hint_origin": "stored_evidence",
        })
    retry_requests = TagEnrichmentRequest.objects.filter(
        place_id__in=place_ids,
        status="queued",
    ).order_by("-updated_at").values("place_id", "context")
    for request in retry_requests:
        place_id = request["place_id"]
        candidate = (request.get("context") or {}).get("codex_candidate_research") or {}
        for source in candidate.get("sources") or []:
            url = str(source.get("url") or "").strip()
            if len(hints[place_id]) >= MAX_SOURCE_HINTS or url in seen[place_id]:
                continue
            if not url.startswith(("http://", "https://")):
                continue
            if urlparse(url).hostname in CODEX_UNREADABLE_HOSTS:
                continue
            seen[place_id].add(url)
            hints[place_id].append({
                "url": url,
                "title": str(source.get("title") or "")[:180],
                "description": str(source.get("snippet") or "")[:500],
                "hint_origin": "page_unavailable_retry",
            })
    jobs = PlaceTagCollectionJob.objects.filter(
        place_id__in=place_ids,
        provider="naver_search",
        status="completed",
        stats__diagnostics__identity_matches__gt=0,
    ).order_by("-cycle_date", "-id").values("place_id", "stats")
    for job in jobs:
        place_id = job["place_id"]
        if len(hints[place_id]) >= MAX_SOURCE_HINTS:
            continue
        for attempt in (job.get("stats") or {}).get("search_attempts") or []:
            for result in attempt.get("results") or []:
                url = str(result.get("url") or "").strip()
                if not result.get("identity_matched") or not url.startswith(("http://", "https://")):
                    continue
                if urlparse(url).hostname in CODEX_UNREADABLE_HOSTS:
                    continue
                if url in seen[place_id]:
                    continue
                seen[place_id].add(url)
                hints[place_id].append({
                    "url": url,
                    "title": str(result.get("title") or "")[:180],
                    "description": str(result.get("description") or "")[:500],
                    "hint_origin": "naver_identity_match",
                })
                if len(hints[place_id]) >= MAX_SOURCE_HINTS:
                    break
            if len(hints[place_id]) >= MAX_SOURCE_HINTS:
                break
    return hints


def seed_row(item):
    place = item["place"]
    district = next((part for part in str(place.address or "").split() if part.endswith(("구", "군"))), "")
    return {
        "place_id": place.id,
        "place_name": place.name,
        "category": place.category,
        "address": place.address,
        "district": district,
        "existing_active_tags": "|".join(item["active_tags"]),
        "target_tag": item["tag"],
        "target_tags": item["target_tags"],
        "target_tag_search_terms": {
            tag: list(TAG_SEARCH_TERMS.get(tag, (tag,)))
            for tag in item["target_tags"]
        },
        "source_hints": item["source_hints"],
        "selection_reason": "launch_quality_gap" if item.get("launch_demand") else "coverage_gap",
        "launch_demand_tags": sorted(item.get("launch_demand") or {}, key=(item.get("launch_demand") or {}).get, reverse=True),
        "corroboration_tags": item.get("corroboration_tags") or [],
        "extracted_tag": "",
        "polarity": "",
        "source_url": "",
        "source_title": "",
        "source_domain": "",
        "source_type": "",
        "evidence_span": "",
        "published_at": "unknown",
        "retrieved_at": "",
        "identity_status": "",
        "identity_confidence": 0,
        "evidence_confidence_candidate": 0,
        "freshness": "unknown",
        "page_verified": False,
        "source_candidate_only": False,
        "candidate_sources": [],
        "failure_detail": "",
        "research_status": "NO_RESULT",
        "notes": "",
    }


def order_missing_tags(
    missing, *, category, demand, allocation, category_tags, corroboration=(),
):
    """Rank useful/researchable gaps before using allocation as a tie-breaker."""
    corroboration = set(corroboration)
    return sorted(
        missing,
        key=lambda value: (
            -int(demand.get(value, 0)),
            0 if value in corroboration else 1,
            RESEARCHABILITY_INDEX.get(value, len(RESEARCHABILITY_INDEX)),
            allocation[(category, value)],
            category_tags.index(value),
        ),
    )


def corroboration_tags(observations):
    """Return positive web tags that need one more independent URL."""
    positive_sources = defaultdict(set)
    negative_tags = set()
    for row in observations or ():
        if row.get("source") not in WEB_EVIDENCE_SOURCES:
            continue
        tag = str(row.get("tag_name") or row.get("tag__name") or "").strip()
        reference = str(row.get("source_reference") or "").strip()
        if not tag or not reference:
            continue
        if row.get("polarity") == "positive":
            positive_sources[tag].add(reference)
        elif row.get("polarity") == "negative":
            negative_tags.add(tag)
    return [
        tag for tag, references in positive_sources.items()
        if len(references) == 1 and tag not in negative_tags
    ]
