import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recommendations.management.commands.process_tag_enrichment_queue import save_place_candidate_evidence
from recommendations.services.codex_web_evidence_validator import validate_candidate


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
        saved = 0
        for row in rows:
            result = validate_candidate(row, live_verify=options["live_verify"])
            counts[result["status"]] += 1
            if result["reason"]:
                reasons[result["reason"]] += 1
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
                saved += int(created)
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
            "reasons": dict(reasons),
        }, ensure_ascii=False, indent=2))
