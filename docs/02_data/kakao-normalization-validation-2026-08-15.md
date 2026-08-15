# Kakao normalization validation — 2026-08-15

The resumable matcher was exercised against the live Kakao Local API using the
first 20 active records from the nationwide library standard dataset.

## Result

- Source rows read: 20
- API requests: 40 (at most two query variants per row)
- Confirmed: 10
- Ambiguous: 4
- Unmatched: 6
- Errors: 0
- Automatically linked rows: confirmed rows only

The confirmed cases had combined name, address, and coordinate evidence with
scores from 86 to 91. Lower name agreement stayed ambiguous or unmatched even
when coordinates were close. This verifies that location alone does not create
an automatic link.

## Cache and resume checks

Repeating the same 20-row batch with `--refresh --dry-run` produced the same
10/4/6 classification using 40 cache hits and zero API requests. The command
also reports `last_id`, has an explicit request ceiling, and preserves an
existing confirmed match when a later refresh produces a weaker outcome.

Automated matcher tests passed (8 tests), covering strong confirmation, close
candidate ambiguity, branch conflicts, low-score rejection, cache reuse,
confirmed-match preservation, and quota/resume behavior.
