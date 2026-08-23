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
    active = defaultdict(set)
    for place_id, tag in PlaceTagEvidence.objects.filter(
        place_id__in=[place.id for place in places], tag__name__in=tags, polarity="positive",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).values_list("place_id", "tag__name"):
        active[place_id].add(tag)
    selected = []
    seen_names = set()
    for place in places:
        normalized_name = "".join(str(place.name or "").lower().split())
        if len(normalized_name) < 3 or normalized_name in seen_names:
            continue
        missing = [tag for tag in tags if tag not in active[place.id]]
        if not missing:
            continue
        tag = min(missing, key=lambda value: (allocation[(category, value)], tags.index(value)))
        allocation[(category, tag)] += 1
        seen_names.add(normalized_name)
        selected.append({"place": place, "tag": tag, "active_tags": sorted(active[place.id])})
        if len(selected) >= limit:
            break
    return selected


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
