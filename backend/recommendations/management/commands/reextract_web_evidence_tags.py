import hashlib
import json
from collections import Counter

from django.core.management.base import BaseCommand

from recommendations.models import PlaceTagEvidence, Tag
from recommendations.services.naver_tag_evidence_provider import polarity_assessment
from recommendations.services.place_tag_collection import requested_tags_for_category
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES


class Command(BaseCommand):
    help = "Re-run current canonical rules over stored web title/snippet without external calls."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, **options):
        queryset = PlaceTagEvidence.objects.filter(
            source__in=WEB_EVIDENCE_SOURCES,
        ).select_related("place", "tag").order_by("id")
        if options["limit"]:
            queryset = queryset[:max(1, options["limit"])]

        existing = set(PlaceTagEvidence.objects.filter(
            source__in=WEB_EVIDENCE_SOURCES,
        ).exclude(source_reference="").values_list("place_id", "tag_id", "source_reference"))
        tags = {tag.name: tag for tag in Tag.objects.all()}
        planned = {}
        scanned = 0
        by_tag = Counter()
        for evidence in queryset.iterator(chunk_size=options["batch_size"]):
            scanned += 1
            title = str((evidence.context or {}).get("source_title") or "")
            text = "{} {}".format(title, evidence.evidence or "").strip()
            if not text or not evidence.source_reference:
                continue
            for tag_name in requested_tags_for_category(evidence.place.category):
                tag = tags.get(tag_name)
                if tag is None:
                    continue
                dedupe = (evidence.place_id, tag.id, evidence.source_reference)
                if dedupe in existing or dedupe in planned:
                    continue
                extraction = polarity_assessment(tag_name, text, category=evidence.place.category)
                polarity = extraction["polarity"]
                if polarity == "unknown":
                    continue
                key_value = "{}|{}|{}|{}|{}".format(
                    evidence.place_id, tag.id, evidence.source,
                    evidence.source_reference, polarity,
                )
                planned[dedupe] = PlaceTagEvidence(
                    place_id=evidence.place_id,
                    tag_id=tag.id,
                    evidence_key=hashlib.sha256(key_value.encode("utf-8")).hexdigest(),
                    source=evidence.source,
                    source_reference=evidence.source_reference,
                    polarity=polarity,
                    confidence=min(evidence.confidence, extraction["clarity_score"]),
                    evidence=evidence.evidence,
                    context={
                        **(evidence.context or {}),
                        "extraction": extraction,
                        "reextracted_from_evidence_id": evidence.id,
                        "reextracted_with_canonical_rules": True,
                    },
                    raw=evidence.raw,
                    observed_at=evidence.observed_at,
                    expires_at=evidence.expires_at,
                )
                by_tag[tag_name] += 1

        created = 0
        if options["apply"] and planned:
            rows = list(planned.values())
            PlaceTagEvidence.objects.bulk_create(
                rows, batch_size=options["batch_size"], ignore_conflicts=True,
            )
            keys = [row.evidence_key for row in rows]
            created_rows = list(PlaceTagEvidence.objects.filter(evidence_key__in=keys).select_related("place", "tag"))
            created = len(created_rows)
            for row in created_rows:
                aggregate_tag_evidence(row.place, row.tag)

        self.stdout.write(json.dumps({
            "mode": "apply" if options["apply"] else "dry_run",
            "scanned_web_evidence": scanned,
            "additional_evidence_rows": len(planned),
            "additional_place_tag_pairs": len({
                (row.place_id, row.tag_id) for row in planned.values()
            }),
            "created_evidence": created,
            "api_calls": 0,
            "by_tag": dict(by_tag.most_common()),
        }, ensure_ascii=False, indent=2))
