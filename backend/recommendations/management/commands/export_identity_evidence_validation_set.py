import csv
import json
from collections import defaultdict, deque
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recommendations.models import PlaceTagCollectionJob, PlaceTagEvidence
from recommendations.services.tag_source_policy import WEB_EVIDENCE_SOURCES


FIELDS = (
    "sample_type", "place_id", "category", "place_name", "place_address",
    "tag", "polarity", "evidence", "source_url", "identity_score",
    "diagnostic_reason", "identity_correct", "evidence_about_place",
    "tag_supported", "polarity_correct", "review_notes",
)


class Command(BaseCommand):
    help = "Export a human-label validation set for identity, evidence support, tag, and polarity."

    def add_arguments(self, parser):
        parser.add_argument("--latest", type=int, default=500)
        parser.add_argument("--diagnostics", default="tmp/identity_mismatch_before.csv")
        parser.add_argument("--output", default="tmp/identity_evidence_validation_150.csv")
        parser.add_argument("--size", type=int, default=150)

    def handle(self, *args, **options):
        size = max(100, min(200, options["size"]))
        job_ids = PlaceTagCollectionJob.objects.order_by("-id").values_list("id", flat=True)[:options["latest"]]
        place_ids = PlaceTagCollectionJob.objects.filter(id__in=job_ids).values_list("place_id", flat=True)
        evidence_rows = []
        for evidence in PlaceTagEvidence.objects.filter(
            place_id__in=place_ids,
            source__in=WEB_EVIDENCE_SOURCES,
        ).select_related("place", "tag").order_by("place__category", "place_id", "id"):
            identity = (evidence.context or {}).get("identity") or {}
            evidence_rows.append({
                "sample_type": "accepted_evidence",
                "place_id": evidence.place_id,
                "category": evidence.place.category,
                "place_name": evidence.place.name,
                "place_address": evidence.place.address,
                "tag": evidence.tag.name,
                "polarity": evidence.polarity,
                "evidence": evidence.evidence,
                "source_url": evidence.source_reference,
                "identity_score": identity.get("score", ""),
                "diagnostic_reason": "",
            })
        diagnostic_path = Path(options["diagnostics"]).resolve()
        if not diagnostic_path.exists():
            raise CommandError(f"Diagnostic CSV not found: {diagnostic_path}")
        with diagnostic_path.open(newline="", encoding="utf-8-sig") as handle:
            mismatch_rows = [{
                "sample_type": "rejected_identity",
                "place_id": row["place_id"],
                "category": row["category"],
                "place_name": row["place_name"],
                "place_address": row["place_address"],
                "tag": "",
                "polarity": "",
                "evidence": row["result_summary"],
                "source_url": row["source_url"],
                "identity_score": row["identity_score"],
                "diagnostic_reason": row["reason"],
            } for row in csv.DictReader(handle)]
        evidence_target = min(len(evidence_rows), size // 2)
        selected = stratified(evidence_rows, evidence_target, key=lambda row: row["category"])
        selected += stratified(
            mismatch_rows,
            size - len(selected),
            key=lambda row: "{}/{}".format(row["category"], row["diagnostic_reason"]),
        )
        for row in selected:
            for label in ("identity_correct", "evidence_about_place", "tag_supported", "polarity_correct", "review_notes"):
                row[label] = ""
        output = Path(options["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(selected)
        self.stdout.write(json.dumps({
            "output": str(output),
            "rows": len(selected),
            "accepted_evidence": sum(row["sample_type"] == "accepted_evidence" for row in selected),
            "rejected_identity": sum(row["sample_type"] == "rejected_identity" for row in selected),
        }, ensure_ascii=False))


def stratified(rows, limit, *, key):
    pools = defaultdict(deque)
    for row in rows:
        pools[key(row)].append(row)
    selected = []
    while pools and len(selected) < limit:
        for group in sorted(list(pools)):
            if len(selected) >= limit:
                break
            selected.append(pools[group].popleft())
            if not pools[group]:
                del pools[group]
    return selected
