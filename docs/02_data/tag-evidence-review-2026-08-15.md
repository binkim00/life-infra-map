# Subjective evidence review validation — 2026-08-15

The Naver provider was enabled only after the confirmed nationwide sample queue
was built. A bounded 120-request batch was processed and then exported with:

    python manage.py export_tag_evidence_review \
        --output tmp/tag_evidence_review.csv \
        --report tmp/tag_evidence_review_report.json

## Result

- Completed requests: 120
- Requests with insufficient identity/tag evidence: 96
- Stored URL-scoped observations: 36
- Active observations after the 120-day expiry rule: 7
- Active place/tag pairs: 7
- Positive/negative conflict rate: 0.0
- Active candidate aggregates: 7
- Automatically confirmed web-only tags: 0
- Manual precision: pending (`null`) until a reviewer fills `manual_correct`

The difference between stored and active observations is expected: historical
blog dates are honored, so observations already older than 120 days are retained
for audit but excluded from the default review and current aggregate. The CSV
contains blank `manual_correct` and `manual_note` columns; feeding that reviewed
file back through `--labels` calculates overall and per-tag precision.

Search-result duplicates are now collapsed by source URL before evidence is
returned, so multiple result entries cannot be counted as independent support.
The generated CSV and JSON remain in the gitignored `backend/tmp/` review area.
