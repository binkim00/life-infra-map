#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def value(data, *keys, default=0):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current or current[key] is None:
            return default
        current = current[key]
    return current


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    collection = payload["collection"]
    naver = collection["naver"]
    web = collection["codex_web"]
    tags = collection["aggregate_tags"]
    runs = payload["codex_runs"]
    quality = payload.get("quality") or {}
    reasons = sorted((runs.get("reasons") or {}).items(), key=lambda item: -item[1])[:5]
    reason_text = ", ".join("{} {}\uac74".format(name, count) for name, count in reasons) or "\uc5c6\uc74c"
    unknown = "\uc9d1\uacc4 \uc804"
    ready = value(quality, "release_gate", "ready", default=False)
    ready_text = "\ud1b5\uacfc" if ready else "\ubbf8\ud1b5\uacfc (\uc5f0\uc18d {}\uc77c)".format(value(quality, "release_gate", "consecutive_ready_days"))
    lines = [
        "\uc5ec\uae30\uc77c\uc9c0\ub3c4 \uc77c\uc77c \uc218\uc9d1 \ubcf4\uace0\uc11c ({})".format(collection["date"]),
        "", "[\ub124\uc774\ubc84 \ube14\ub85c\uadf8 \uc218\uc9d1]",
        "- \uacc4\ud68d/\uc644\ub8cc: {} / {}\uacf3".format(naver["planned_jobs"], naver["completed_jobs"]),
        "- \uc720\ud6a8/\uadfc\uac70 \ubd80\uc871/\uc2e4\ud328: {} / {} / {}\uacf3".format(naver["useful_jobs"], naver["insufficient_jobs"], naver["failed_jobs"]),
        "- API \uc694\uccad: {}\ud68c (\uc81c\ud55c \uc751\ub2f5 {}\ud68c)".format(naver["api_requests"], naver["rate_limited_requests"]),
        "- \uc624\ub298 \uc2e0\uaddc \uadfc\uac70: {}\uac1c, \uc7a5\uc18c {}\uacf3, \ud0dc\uadf8 \uc885\ub958 {}\uac1c".format(naver["new_evidence_rows"], naver["new_evidence_places"], naver["new_evidence_tags"]),
        "", "[Codex \uc6f9 \uc870\uc0ac]",
        "- \uc2e4\ud589/\uac80\uc0ac \ud6c4\ubcf4: {}\ud68c / {}\uac1c".format(runs["runs"], runs["rows"]),
        "- \ucc44\ud0dd/\ud655\uc778 \ud544\uc694/\ud0c8\ub77d: {} / {} / {}\uac1c".format(runs["accepted"], runs["needs_verification"], runs["rejected"]),
        "- \uc0c8\ub85c \uc800\uc7a5: {}\uac1c (\uc8fc \uadfc\uac70 {}, \uad00\ub828 \ud0dc\uadf8 \ud30c\uc0dd {})".format(runs["saved"], runs.get("primary_saved", runs["saved"]), runs.get("related_saved", 0)),
        "- \uc624\ub298 DB \uc2e0\uaddc \uadfc\uac70: {}\uac1c, \uc7a5\uc18c {}\uacf3".format(web["new_evidence_rows"], web["new_evidence_places"]),
        "- \uc8fc\uc694 \ud0c8\ub77d \uc0ac\uc720: {}".format(reason_text),
        "", "[\uac80\uc0c9 \ud488\uc9c8 \ubc18\uc601]",
        "- \uc624\ub298 \uc2e0\uaddc \ud1b5\ud569 \ud0dc\uadf8: {}\uac1c, \uc7a5\uc18c {}\uacf3".format(tags["new_place_tags"], tags["new_tagged_places"]),
        "- \uac80\uc0c9 \uac00\ub2a5 \uc7a5\uc18c \uc99d\uac10: \uce74\ud398 {}, \uc2dd\ub2f9 {}".format(value(quality, "daily_delta", "cafe_searchable_places", default=unknown), value(quality, "daily_delta", "restaurant_searchable_places", default=unknown)),
        "- \uc870\uac74 \uac80\uc0c9 hit@5: {}".format(value(quality, "search", "feature_query_hit_at_5_rate", "value", default=unknown)),
        "- \uac80\uc99d \uadfc\uac70 \uacb0\uacfc \ube44\uc728@5: {}".format(value(quality, "search", "verified_feature_result_rate_at_5", "value", default=unknown)),
        "- \ud558\ub4dc \uc870\uac74 \uc704\ubc18\ub960: {}".format(value(quality, "search", "hard_violation_rate", "value", default=unknown)),
        "- 1\ucc28 \ubc30\ud3ec \uac8c\uc774\ud2b8: {}".format(ready_text),
        "", "\uc0dd\uc131 \uc2dc\uac01: {}".format(collection["generated_at"]),
    ]
    Path(args.output).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
