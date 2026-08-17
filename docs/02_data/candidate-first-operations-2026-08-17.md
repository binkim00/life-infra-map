# Candidate-first evidence operations (2026-08-17)

## Operating policy

Daily bootstrap planning now separates request-budget buckets instead of treating
all targeted work as one pool:

| Bucket | Initial weight |
| --- | ---: |
| candidate hint validation | 45 |
| cafe discovery | 25 |
| NO_TAG targeted recovery | 15 |
| high-quality restaurant | 5 |
| exploration | 9 |
| stale web refresh | 1 |

`PlaceTag` candidate rows are search hints only. The planner prefers a candidate
whose same canonical Tag lacks active Evidence, but the collector still requires
a matched Naver result and a grounded expression before saving
`PlaceTagEvidence`. Web-only results retain the existing candidate or
needs-verification aggregation policy and never become confirmed automatically.

Unused candidate budget falls back to cafe discovery before NO_TAG, restaurant,
exploration, and stale refresh. A bucket with at least 200 measured calls can
adjust by its active-Evidence yield, bounded to 0.5–1.5x. Scaling increases only
after three stable cycles with no 429 and acceptable yield; otherwise it holds
or decreases. The production `.env` place limit was not raised by this change.

The 7,500-place dry-run uses the measured 1.0159 calls/place and estimates 7,620
Naver calls (30.48% of the 25,000 daily quota). This is a capacity estimate, not
an automatic operating-setting change.

## Bounded collection result

The remaining same-day unattempted candidate pool contained only 84 pairs. The
adopted WORK pack could safely address 18 Busan cafe places and the ambience pack
one Seoul cafe place; the batch was not padded with general discovery.

- Candidate WORK: 18 calls, identity 18/18, 16 Evidence places, 53 observations,
  7 new Evidence, 1 new active Evidence, 1 new PlaceTag, no failure/429.
- Seoul ambience: 1 call, identity mismatch, no Evidence saved.
- NO_TAG/AI experiment: 149 unattempted places available (12 Seoul, 137 Busan),
  149 Naver calls, 19 OpenAI calls, 9 grounded/stored AI Evidence, 3 current AI
  Evidence, 0 invalid outputs, 0 Naver failure/429.

The requested 500-place AI ceiling was not filled because the eligible,
same-day-unattempted cafe NO_TAG pool was exhausted and no eligible restaurant
NO_TAG pool existed. Re-querying the same place on the same day was deliberately
blocked.

Exact metered usage for the new AI calls was 5,983 input, 6,828 output, and
12,811 total tokens. Using the official GPT-5 nano rates at the run date, the
derived cost was USD 0.00287655. The first 28 historical calls predated usage
metering and remain unmeasured. The runtime default stays disabled with a daily
limit of 100 calls, minimum identity score 70, one call/place, explicit allowed
canonical Tags, verbatim span validation, and category-profile validation.

Human review can be sampled with:

```text
python manage.py export_ai_evidence_validation \
  --limit 30 --output tmp/ai_evidence_validation_final_30.csv
```

The review columns are blank by design; the command does not manufacture labels.

## Coverage change

The run started at 197,142 Evidence / 139,132 active Evidence / 706,789
PlaceTags and ended at 197,203 / 139,143 / 706,798. Evidence-holding Places rose
from 156,650 to 156,679.

Seoul cafe remained 677 Evidence Places and 147 active Evidence Places because
the eligible Seoul pool was nearly exhausted. Busan cafe increased from 1,188 to
1,217 Evidence Places and from 540 to 547 active Evidence Places. Busan active
Tag Places changed as follows: work-friendly 21→22, laptop 99→101, outlet 14→19,
and free Wi-Fi 5→6. Other reported cafe/restaurant active counts were unchanged.

## Search and source conclusions

The 33-case AI-off regression (11 queries × 3 variants) returned results in all
cases with zero hard violations and zero fallbacks. Average latency was 577.64ms,
median 434.11ms, p95 1,613.30ms, and max 2,152.89ms; DB retrieval averaged
570.90ms.

The [official public Wi-Fi API](https://www.data.go.kr/data/15155062/openapi.do)
is high-confidence for public access-point Places, but proximity
does not prove that a cafe provides Wi-Fi. Starbucks and Hollys expose official
store/service filters ([Starbucks](https://www.starbucks.co.kr/store/store_map.do?disp=local),
[Hollys](https://www.hollys.co.kr/store/korea/korStore.do)), yet automated bulk reuse terms were not established, so
no brand adapter was added. Official-source matching remains the preferred next
path for Wi-Fi, outlets, operating hours, and parking when store-level reuse is
explicitly permitted.
