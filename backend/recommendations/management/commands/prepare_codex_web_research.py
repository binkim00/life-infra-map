import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from recommendations.models import Place, PlaceTagCollectionJob, PlaceTagEvidence
from recommendations.services.restaurant_collection_quality import restaurant_collection_quality
from recommendations.services.web_tag_evidence_provider import CATEGORY_TAGS
from recommendations.services.place_evidence_completeness import target_tags_for_gaps


MAX_TARGET_TAGS = 8
MAX_SOURCE_HINTS = 5

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


class Command(BaseCommand):
    help = "Prepare a Busan-only Codex web research seed file without calling providers."

    def add_arguments(self, parser):
        parser.add_argument("--cafe", type=int, default=50)
        parser.add_argument("--restaurant", type=int, default=50)
        parser.add_argument("--output", default="tmp/codex_web_evidence_busan_pilot.json")
        parser.add_argument("--exclude-place-ids", default="")

    def handle(self, *args, **options):
        selected = []
        allocation = Counter()
        excluded = {
            int(value) for value in str(options["exclude_place_ids"] or "").split(",")
            if value.strip().isdigit()
        }
        for category in ("cafe", "restaurant"):
            limit = max(0, int(options[category]))
            rows = select_places(category, limit, allocation, exclude_place_ids=excluded)
            if len(rows) < limit:
                raise CommandError("Only {} eligible {} places found".format(len(rows), category))
            selected.extend(rows)
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
            "categories": dict(Counter(row["place"].category for row in selected)),
            "target_tags": dict(Counter(row["tag"] for row in selected)),
            "json": str(path), "csv": str(csv_path),
        }, ensure_ascii=False))


def select_places(category, limit, allocation, *, exclude_place_ids=None):
    tags = CATEGORY_TAGS[category]
    exclude_place_ids = exclude_place_ids or set()
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
    ).filter(identity_success=True).order_by("-no_tag", "-evidence_success", "name")[:5000])
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
                key=lambda item: (-item[0], -int(item[1].evidence_success), -int(item[1].no_tag), item[1].name),
            )
        ]
    else:
        places.sort(key=lambda place: (-int(place.evidence_success), -int(place.no_tag), place.name))
    active = defaultdict(list)
    for row in PlaceTagEvidence.objects.filter(
        place_id__in=[place.id for place in places],
        tag__name__in=tags,
        polarity__in=("positive", "negative"),
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).values(
        "place_id", "tag__name", "polarity", "source", "source_reference",
    ):
        active[row["place_id"]].append({**row, "tag_name": row["tag__name"]})
    source_hints = source_hints_for_places([place.id for place in places])
    selected = []
    seen_names = set()
    for place in places:
        normalized_name = "".join(str(place.name or "").lower().split())
        if len(normalized_name) < 3 or normalized_name in seen_names:
            continue
        missing = [
            tag for tag in target_tags_for_gaps(category, active[place.id], limit=len(tags))
            if tag in tags
        ]
        if not missing:
            continue
        ordered_missing = sorted(
            missing,
            key=lambda value: (
                allocation[(category, value)],
                RESEARCHABILITY_INDEX.get(value, len(RESEARCHABILITY_INDEX)),
                tags.index(value),
            ),
        )
        tag = ordered_missing[0]
        allocation[(category, tag)] += 1
        seen_names.add(normalized_name)
        selected.append({
            "place": place,
            "tag": tag,
            "target_tags": [tag] + [value for value in ordered_missing if value != tag][:MAX_TARGET_TAGS - 1],
            "active_tags": sorted({row["tag_name"] for row in active[place.id]}),
            "source_hints": source_hints.get(place.id, []),
        })
        if len(selected) >= limit:
            break
    return selected


def source_hints_for_places(place_ids):
    hints = defaultdict(list)
    seen = defaultdict(set)
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
                if url in seen[place_id]:
                    continue
                seen[place_id].add(url)
                hints[place_id].append({
                    "url": url,
                    "title": str(result.get("title") or "")[:180],
                    "description": str(result.get("description") or "")[:500],
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
        "source_hints": item["source_hints"],
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
        "research_status": "NO_RESULT",
        "notes": "",
    }
