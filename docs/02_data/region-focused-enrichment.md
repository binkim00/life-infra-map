# Region-focused cafe/restaurant enrichment

The bootstrap collector keeps one focus region while Balanced Mode remains available for long-term nationwide coverage.

## Current sequence

`부산 -> 서울 -> 인천 -> 대구 -> 대전 -> 광주 -> 울산`

`TAG_COLLECTION_FOCUS_REGION` defaults to `부산광역시`. In bootstrap mode the scheduler limits new jobs to `TAG_COLLECTION_FOCUS_CATEGORIES`, which defaults to `cafe,restaurant`. Changing the focus region is an explicit configuration change; the calendar does not advance it.

## Cycle workflow

1. Run `python manage.py report_region_enrichment 부산`.
2. Plan a bounded bootstrap batch with `--regions 부산광역시 --categories cafe,restaurant`.
3. Evaluate calls, active/API, failures, 429, mismatch, no-result, and no-tag.
4. Keep stale refresh within its hard request cap, calculated from the bounded cycle request budget rather than the provider's remaining daily quota.
5. Increase budget only after three stable cycles. Do not move regions while high-priority pools remain productive.

Candidate hints only prioritize searches. They never become Evidence directly. Active coverage counts only current positive Evidence. Semantic retrieval and operating pgvector remain unchanged and OFF.
