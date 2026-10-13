"""Opt-in, redacted diagnostics for a single search candidate pipeline."""

import hashlib
import json
import logging
import uuid


logger = logging.getLogger("recommendations.search_candidate_trace")


def _identities(candidate):
    return {str(value) for value in [candidate.get("id"), *(candidate.get("duplicate_candidate_ids") or [])] if value}


def build_candidate_trace(*, db, kakao, web, gate_kept, gate_removed, ranked, results):
    """Keep stage evidence separate from PlaceTag status and omit source text."""
    salt = uuid.uuid4().hex
    rows = {}

    def mark(candidates, stage):
        for candidate in candidates or []:
            if not isinstance(candidate, dict):
                continue
            identities = _identities(candidate)
            if not identities:
                continue
            keys = [value for value in identities if value in rows] or [sorted(identities)[0]]
            for key in keys:
                mark_one(candidate, stage, key)

    def mark_one(candidate, stage, key):
        source = str(candidate.get("candidate_source") or "unknown")
        row = rows.setdefault(key, {
            "candidate": hashlib.sha256((salt + key).encode()).hexdigest()[:16],
            "source": source if source in {"db", "kakao", "web", "semantic"} else "unknown",
            "internal_place_linked": False,
            "identity_status": "unattempted",
            "confirmed_place_tag_count": 0,
            "active_evidence_tag_count": 0,
            "stages": [],
            "gate_reasons": [],
            "final_rank": None,
            "score": None,
        })
        if stage not in row["stages"]:
            row["stages"].append(stage)
        row["internal_place_linked"] |= bool(candidate.get("place_id"))
        status = candidate.get("identity_lookup_status")
        if status in {
            "exact_external_id_and_identity", "exact_identity", "ambiguous",
            "no_match", "insufficient_identity", "invalid_coordinates",
        }:
            row["identity_status"] = status
        row["confirmed_place_tag_count"] = max(
            row["confirmed_place_tag_count"], len(candidate.get("verified_tags") or []),
        )
        row["active_evidence_tag_count"] = max(
            row["active_evidence_tag_count"], len(candidate.get("hard_gate_active_tags") or []),
        )
        for violation in candidate.get("hard_gate_violations") or []:
            reason = violation.get("type")
            if reason in {"category", "region", "feature"} and reason not in row["gate_reasons"]:
                row["gate_reasons"].append(reason)
        if stage == "final":
            row["final_rank"] = candidate.get("backend_rank")
        if stage in {"ranked", "final"} and isinstance(candidate.get("score"), (int, float)):
            row["score"] = round(candidate["score"], 2)

    for stage, candidates in (
        ("db", db), ("kakao", kakao), ("web", web),
        ("gate_pass", gate_kept), ("gate_reject", gate_removed),
        ("ranked", ranked), ("final", results),
    ):
        mark(candidates, stage)
    candidates = list(rows.values())
    return {
        "schema": 1,
        "counts": {
            "db": len(db or []), "kakao": len(kakao or []), "web": len(web or []),
            "internal_place_linked": sum(row["internal_place_linked"] for row in candidates),
            "confirmed_place_tag": sum(row["confirmed_place_tag_count"] > 0 for row in candidates),
            "active_evidence_join": sum(row["active_evidence_tag_count"] > 0 for row in candidates),
            "kakao_internal_match": sum(row["source"] == "kakao" and row["internal_place_linked"] for row in candidates),
            "web_internal_match": sum(row["source"] == "web" and row["internal_place_linked"] for row in candidates),
            "gate_pass": len(gate_kept or []), "gate_reject": len(gate_removed or []),
            "ranked": len(ranked or []), "final": len(results or []),
        },
        "candidates": candidates,
    }


def log_candidate_trace(**stages):
    try:
        logger.warning("search_candidate_trace %s", json.dumps(build_candidate_trace(**stages), separators=(",", ":")))
    except Exception:
        logger.warning("Search candidate trace failed; search results are preserved.")
