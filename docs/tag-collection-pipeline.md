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
