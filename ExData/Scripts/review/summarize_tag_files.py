import json
from collections import Counter, defaultdict
from pathlib import Path

TAGS_DIR = Path(r"C:\Users\k0b03\Desktop\영빈\SSAFY\life-infra-map\backend\recommendations\fixtures\tags")
OUTPUT_PATH = TAGS_DIR / "_tag_files_summary_for_review.json"

summaries = {}

for path in TAGS_DIR.glob("*.json"):
    if path.name.startswith("_"):
        continue

    print(f"처리 중: {path.name}")

    with path.open("r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list):
        summaries[path.name] = {
            "error": "list 구조가 아님",
            "type": type(rows).__name__,
        }
        continue

    tag_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    tag_type_counter = Counter()
    confidence_counter = Counter()
    place_tags = defaultdict(list)

    for row in rows:
        tag_name = row.get("tag_name") or row.get("name")
        source = row.get("source") or row.get("tag_source")
        status = row.get("status")
        tag_type = row.get("tag_type")
        confidence = row.get("confidence")

        place_key = (
            row.get("place_source") or row.get("external_source"),
            row.get("place_external_id") or row.get("external_id"),
            row.get("place_name"),
        )

        if tag_name:
            tag_counter[tag_name] += 1
            place_tags[place_key].append(tag_name)

        if source:
            source_counter[source] += 1

        if status:
            status_counter[status] += 1

        if tag_type:
            tag_type_counter[tag_type] += 1

        try:
            confidence = int(float(confidence))
        except (TypeError, ValueError):
            confidence = None

        if confidence is not None:
            if confidence >= 90:
                confidence_counter["90-100"] += 1
            elif confidence >= 70:
                confidence_counter["70-89"] += 1
            elif confidence >= 50:
                confidence_counter["50-69"] += 1
            else:
                confidence_counter["0-49"] += 1

    summaries[path.name] = {
        "row_count": len(rows),
        "place_count": len(place_tags),
        "unique_tag_count": len(tag_counter),
        "avg_tags_per_place": round(len(rows) / len(place_tags), 2) if place_tags else 0,
        "tag_counts_top_100": dict(tag_counter.most_common(100)),
        "source_counts": dict(source_counter),
        "status_counts": dict(status_counter),
        "tag_type_counts": dict(tag_type_counter),
        "confidence_counts": dict(confidence_counter),
        "sample_places": [
            {
                "place_source": key[0],
                "place_external_id": key[1],
                "place_name": key[2],
                "tags": tags[:30],
            }
            for key, tags in list(place_tags.items())[:20]
        ],
    }

with OUTPUT_PATH.open("w", encoding="utf-8") as f:
    json.dump(summaries, f, ensure_ascii=False, indent=2)

print(f"요약 저장 완료: {OUTPUT_PATH}")