# Place tag collection pipeline

## Purpose

Nationwide search starts with objective tags from official place data and gets
better through real search demand and user evidence. Search behavior is never
treated as verified ground truth by itself.

## Evidence layers

1. Official fields create high-confidence objective tags.
2. Place-name rules create low-confidence candidates.
3. Natural-language searches record requested tags as demand, even for guests.
4. Result impressions, clicks, saves, and explicit rejections record weak
   behavioral signals for a place within that search.
5. `맞아요` and `아니에요` feedback creates positive or negative evidence.

The React client creates an anonymous random session ID. Django stores only its
SHA-256 hash. An authenticated user may also be linked when a valid token is
present. Client event keys make retries idempotent.

## API

Send one to fifty events at a time:

    POST /api/recommendations/interactions/

Example search demand:

    {
      'events': [{
        'event_type': 'search',
        'session_key': 'random-browser-session',
        'search_id': 'random-search-id',
        'query': '서면 분위기 좋은 브런치 카페',
        'requested_tags': ['분위기 좋은', '브런치']
      }]
    }

Place events include a canonical `place_id` when known. Kakao-only candidates
retain their external identity until a canonical place match becomes available.

## Aggregation rules

Explicit feedback is aggregated immediately after the API write:

- three distinct actors and a positive margin of at least two confirm a tag;
- the corresponding negative rule rejects it;
- every direct vote becomes a `PlaceTagEvidence` row with provenance;
- the latest vote from the same actor wins.

Behavioral signals are deliberately weaker:

- click: +1
- save: +3
- explicit result rejection: -2
- at least five distinct actors are required;
- the result remains a candidate and is never marked user-verified.

Run the complete behavioral rebuild from a scheduler:

    python manage.py aggregate_place_tag_interactions

Use `--dry-run` to inspect counts without updating tags.

## Product collection points

The Home search automatically records search demand, clarification answers, and the first twenty unique
impressions. Place selection records a click, successful saving records a save,
and each result has an explicit rejection action. The place detail panel offers
up to five tag confirmation rows, prioritizing tags requested in the current
natural-language query and filling remaining rows with category defaults.

This supplies nationwide cold-start demand without inventing subjective facts:
objective tags work on day one, while subjective tags become reliable only as
independent evidence accumulates.

## Nationwide stratified bootstrap queue

Create the subjective-evidence bootstrap sample only after Kakao normalization:

    python manage.py build_nationwide_tag_enrichment_sample \
        --per-stratum 5 \
        --categories cafe,restaurant,tourism,city_park \
        --dry-run

The default matrix is 17 provinces/cities by four categories. Sampling is spread
across the available ID range inside each stratum and deduplicated by Kakao
canonical place. A staged source record is eligible only when all of the
following hold:

- the source record is active;
- `KakaoPlaceMatch.status` is `confirmed`;
- `normalized_place.source` is `kakao_local`;
- the category is cafe, restaurant, tourism, or city park.

Direct Kakao registry places satisfy the same identity requirement without an
extra source-match row. The nationwide queue's current coverage and intentionally
unfilled strata are recorded in
[`docs/02_data/nationwide-tag-sample-2026-08-15.md`](02_data/nationwide-tag-sample-2026-08-15.md).

The command reports covered and missing strata so an incomplete regional source
registry cannot silently look nationwide. Existing queue rows are idempotently
reused, and already confirmed user-verified tags are skipped. Do not enable the
enrichment worker until the dry-run shows acceptable nationwide coverage.

## Evidence review and promotion

Export active web evidence and a tag-level report:

    python manage.py export_tag_evidence_review \
        --output tmp/tag_evidence_review.csv \
        --report tmp/tag_evidence_review_report.json

The CSV includes place name, address, tag, polarity, source URL, short evidence,
confidence, observation/expiry dates, and blank manual review columns. Fill
`manual_correct` with `맞음/틀림`, `true/false`, or `1/0`, then pass the reviewed
file back through `--labels` to calculate overall and per-tag precision. The JSON
also reports adoption, no-evidence, and positive/negative conflict rates.

The first bounded live-provider validation, including expiry behavior and the
manual-review handoff, is recorded in
[`docs/02_data/tag-evidence-review-2026-08-15.md`](02_data/tag-evidence-review-2026-08-15.md).

Materialize active evidence after collection or review:

    python manage.py aggregate_place_tag_evidence --dry-run

Three independent web URLs increase candidate confidence but never confirm a
tag. Confirmation requires an official positive field, or web evidence combined
with explicit user confirmation or an `admin_review` evidence row. Expired rows
are ignored and active negative rows reduce confidence or block promotion.
Re-aggregation also removes a confirmation previously created by this evidence
path when its support expires; confirmations owned by the separate interaction
aggregator are not deleted. Validation results are recorded in
[`docs/02_data/tag-evidence-promotion-2026-08-15.md`](02_data/tag-evidence-promotion-2026-08-15.md).
