import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.management.commands.process_tag_enrichment_queue import save_place_candidate_evidence
from recommendations.models import TagEnrichmentRequest
from recommendations.services.codex_web_evidence_validator import validate_candidate
from recommendations.services.naver_tag_evidence_provider import polarity_assessment
from recommendations.services.place_tag_collection import requested_tags_for_category


MAX_RELATED_TAGS_PER_EVIDENCE = 4


class Command(BaseCommand):
    help = "Validate Codex-researched web evidence candidates without paid search calls."

    def add_arguments(self, parser):
        parser.add_argument("input")
        parser.add_argument("--live-verify", action="store_true")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        if options["apply"] and not options["live_verify"]:
            raise CommandError("--apply requires --live-verify")
        path = Path(options["input"])
        if not path.exists():
            raise CommandError("Input file does not exist: {}".format(path))
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise CommandError("Input must be a list or an object with a results list.")
        counts = Counter()
        reasons = Counter()
        primary_saved = 0
        related_saved = 0
        requests_completed = 0
        requests_closed_without_evidence = 0
        for row in rows:
            result = validate_candidate(row, live_verify=options["live_verify"])
            counts[result["status"]] += 1
            if result["reason"]:
                reasons[result["reason"]] += 1
            if options["apply"] and result["status"] in {"rejected", "ambiguous"}:
                requests_closed_without_evidence += close_research_requests(row, result["reason"])
            if options["apply"] and result["status"] in {"accepted", "needs_verification"}:
                normalized = result["normalized"]
                evidence = {
                    "source_url": normalized["source_url"],
                    "source_title": normalized["source_title"],
                    "polarity": normalized["polarity"],
                    "confidence": normalized["confidence"],
                    "evidence_summary": normalized["evidence_summary"],
                    "identity": normalized["identity"],
                    "extraction": normalized["extraction"],
                    "confidence_factors": normalized["confidence_factors"],
                    "raw": {
                        "channel": "codex_cli_web_search",
                        "provider": "codex_cli",
                        "source_type": normalized["source_type"],
                        "live_verified": bool(options["live_verify"]),
                    },
                }
                with transaction.atomic():
                    _, created = save_place_candidate_evidence(
                        normalized["place"], normalized["tag_name"], evidence,
                        observed_at=normalized["observed_at"],
                    )
                    primary_saved += int(created)
                    requests_completed += TagEnrichmentRequest.objects.filter(
                        place=normalized["place"],
                        tag_name=normalized["tag_name"],
                    ).exclude(status="completed").update(
                        status="completed", next_attempt_at=None, error_message="",
                    )
                    for related_tag, related_evidence in related_rule_evidences(normalized, evidence):
                        _, related_created = save_place_candidate_evidence(
                            normalized["place"], related_tag, related_evidence,
                            observed_at=normalized["observed_at"],
                        )
                        related_saved += int(related_created)
                        requests_completed += TagEnrichmentRequest.objects.filter(
                            place=normalized["place"], tag_name=related_tag,
                        ).exclude(status="completed").update(
                            status="completed", next_attempt_at=None, error_message="",
                        )
        saved = primary_saved + related_saved
        self.stdout.write(json.dumps({
            "dry_run": not options["apply"],
            "live_verify": options["live_verify"],
            "rows": len(rows),
            "accepted": counts["accepted"],
            "needs_verification": counts["needs_verification"],
            "rejected": counts["rejected"],
            "ambiguous": counts["ambiguous"],
            "duplicate": counts["duplicate"],
            "saved": saved,
            "primary_saved": primary_saved,
            "related_saved": related_saved,
            "requests_completed": requests_completed,
            "requests_closed_without_evidence": requests_closed_without_evidence,
            "reasons": dict(reasons),
        }, ensure_ascii=False, indent=2))


def related_rule_evidences(normalized, evidence):
    """Mine other deterministic category tags from the same verified quote."""
    related = []
    primary_tag = normalized["tag_name"]
    text = evidence["evidence_summary"]
    for tag_name in requested_tags_for_category(normalized["place"].category):
        if tag_name == primary_tag:
            continue
        extraction = polarity_assessment(tag_name, text, category=normalized["place"].category)
        if extraction["polarity"] == "unknown":
            continue
        related.append((tag_name, {
            **evidence,
            "polarity": extraction["polarity"],
            "confidence": min(int(evidence["confidence"]), int(extraction["clarity_score"])),
            "extraction": {
                **extraction,
                "method": "related_rule",
                "derived_from_tag": primary_tag,
            },
            "raw": {
                **(evidence.get("raw") or {}),
                "derived_from_tag": primary_tag,
            },
        }))
        if len(related) >= MAX_RELATED_TAGS_PER_EVIDENCE:
            break
    return related


def close_research_requests(row, reason):
    """Close this run's launch requests; tomorrow's evaluation may queue them again."""
    try:
        place_id = int(row.get("place_id"))
    except (TypeError, ValueError):
        return 0
    research_status = str(row.get("research_status") or reason or "").strip().upper()
    requests = list(TagEnrichmentRequest.objects.filter(place_id=place_id))
    if research_status != "IDENTITY_MISMATCH":
        target_tag = str(row.get("target_tag") or "").strip()
        requests = [request for request in requests if request.tag_name == target_tag]
    closed = 0
    for request in requests:
        context = dict(request.context or {})
        launch = context.get("launch_quality")
        if not isinstance(launch, dict):
            continue
        launch = dict(launch)
        launch["last_research_status"] = research_status or str(reason or "")[:100]
        context["launch_quality"] = launch
        request.status = "failed" if research_status == "IDENTITY_MISMATCH" else "completed"
        request.error_message = "codex_cli:{}".format(reason or research_status)[:1000]
        request.next_attempt_at = None
        request.context = context
        request.save(update_fields=[
            "status", "error_message", "next_attempt_at", "context", "updated_at",
        ])
        closed += 1
    return closed
