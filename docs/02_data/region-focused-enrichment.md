# Region-focused cafe/restaurant enrichment

The bootstrap collector keeps an ordered focus cohort while Balanced Mode remains available for long-term nationwide coverage.

## Current sequence

`부산 우선 -> 서울 -> 수도권 -> 광역시 -> 전국`

API evidence collection currently uses `부산광역시,서울특별시` with a `70,30` split and a daily place limit of 100. In bootstrap mode the scheduler limits new jobs to `TAG_COLLECTION_FOCUS_CATEGORIES`, which defaults to `cafe,restaurant`.

AI web research keeps the staged expansion plan above. Adding Seoul to the bounded API evidence batch does not automatically advance AI web research to the metropolitan, metro-city, or nationwide stages.

## Cycle workflow

1. Run `python manage.py report_region_enrichment 부산`.
2. Plan a bounded bootstrap batch with `--regions 부산광역시 --categories cafe,restaurant`.
3. Evaluate calls, active/API, failures, 429, mismatch, no-result, and no-tag.
4. Keep stale refresh within its hard request cap, calculated from the bounded cycle request budget rather than the provider's remaining daily quota.
5. Increase budget only after three stable cycles. Do not move regions while high-priority pools remain productive.

Candidate hints only prioritize searches. They never become Evidence directly. Active coverage counts only current positive Evidence. Semantic retrieval and operating pgvector remain unchanged and OFF.
