# Nationwide place and evidence pipeline

## Goal

The service must return a useful base result anywhere in Korea and improve
subjective relevance as evidence accumulates. Nationwide scope does not require
copying every commercial map provider record or inventing tags without evidence.

The pipeline separates four concerns:

1. Source registry: preserve official source rows and their update state.
2. Canonical places: normalize, geocode, and deduplicate records used by search.
3. Evidence: retain every objective or subjective tag observation with provenance.
4. Coverage: measure gaps for every administrative area and category.

## Data flow

    LOCALDATA full snapshot
            |
            v
    SourcePlaceRecord ---- daily delta ---- DataSourceSyncRun
            |
            +---- status normalization
            +---- coordinate conversion/geocoding
            +---- deduplication/provider matching
            v
          Place <---- Kakao on-demand discovery
            |
            +---- PlaceTagEvidence (individual facts/opinions)
            v
         PlaceTag (search aggregate)
            |
            v
       PlaceCoverage

`SourcePlaceRecord` is intentionally separate from `Place`. LOCALDATA coordinate
fields can use EPSG:5174 and some rows do not have usable coordinates. Raw rows
must remain recoverable before coordinate conversion and entity matching.

## Source ingestion contract

Every importer must:

- use a stable `source`, `dataset`, and `source_record_id`;
- preserve the normalized raw source row;
- record a SHA-256 checksum and import statistics;
- support full and delta runs;
- update existing records idempotently;
- preserve closed and suspended records instead of deleting them;
- avoid promoting rows to `Place` until coordinates and identity are trustworthy.

Initial LOCALDATA datasets:

| Dataset key | Source dataset | Default category |
|---|---|---|
| `general_restaurant` | General restaurant licenses | `restaurant` |
| `rest_restaurant` | Rest restaurant licenses | `food_service` |
| `bakery` | Bakery licenses | `bakery` |
| `tourist_restaurant` | Tourist restaurant licenses | `restaurant` |

Rest restaurant rows are not all cafes. Only rows with a cafe-specific business
type are classified as `cafe`; ambiguous rows remain `food_service`.

## Commands

Import a full CSV snapshot:

    cd backend
    .\venv\Scripts\python.exe manage.py import_localdata_records C:\data\fulldata_general_restaurant.csv --dataset general_restaurant --sync-type full

Import a delta:

    .\venv\Scripts\python.exe manage.py import_localdata_records C:\data\delta_general_restaurant.csv --dataset general_restaurant --sync-type delta

Validate a sample without writes:

    .\venv\Scripts\python.exe manage.py import_localdata_records C:\data\fulldata_general_restaurant.csv --dataset general_restaurant --dry-run --limit 1000

Rebuild nationwide coverage:

    .\venv\Scripts\python.exe manage.py rebuild_place_coverage --source localdata

Synchronize through the official daily OpenAPI:

    # Add the dataset-specific service key to backend/.env first.
    .\venv\Scripts\python.exe manage.py sync_localdata_api --dataset rest_restaurant

Environment variables:

- `DATA_GO_KR_SERVICE_KEY`: general restaurants
- `DATA_GO_KR_REST_RESTAURANT_SERVICE_KEY`: rest restaurants and cafes
- `DATA_GO_KR_BAKERY_SERVICE_KEY`: bakeries

Apply for each OpenAPI separately in data.go.kr. A key that works for
`general_restaurant` can still receive HTTP 403 for `rest_restaurant` or
`bakery` until those APIs are approved.

The LOCALDATA APIs currently cap responses at 100 rows even when a larger
`numOfRows` is requested. Use the full CSV snapshot for the initial nationwide
load. Use OpenAPI for daily refreshes or resumable batches:

    .\venv\Scripts\python.exe manage.py sync_localdata_api --dataset general_restaurant --max-pages 9000
    .\venv\Scripts\python.exe manage.py sync_localdata_api --dataset general_restaurant --start-page 9001 --max-pages 9000

Keep batches below the approved request quota. The command records the next page
in `DataSourceSyncRun.cursor`.

Promote valid coordinates into searchable places:

    .\venv\Scripts\python.exe manage.py promote_source_places --source localdata

Generate official-field tags and evidence:

    .\venv\Scripts\python.exe manage.py generate_objective_place_tags --source localdata

Then refresh coverage:

    .\venv\Scripts\python.exe manage.py rebuild_place_coverage --source localdata

## Production refresh and monitoring

Run quota-sized API batches for the three enabled datasets and continue from
the cursor saved by the previous batch:

    .\venv\Scripts\python.exe manage.py run_nationwide_sync --max-pages 100

The command synchronizes general restaurants, rest restaurants/cafes, and
bakeries. It then promotes new coordinates, regenerates objective tag evidence,
and rebuilds coverage. A dataset can be selected explicitly, and the enrichment
phase can be deferred when several API batches must run first:

    .\venv\Scripts\python.exe manage.py run_nationwide_sync --dataset bakery --max-pages 100 --skip-enrichment

A successful batch records whether the API dataset was fully exhausted. Until
then, the next invocation resumes from `DataSourceSyncRun.cursor.next_page`.
After exhaustion, the following scheduled refresh starts again at page 1.

Use this command as a scheduler or container health job. It exits non-zero when
a dataset has no recent run, the latest run failed, a run is older than the
allowed age, or no coverage cells exist:

    .\venv\Scripts\python.exe manage.py check_nationwide_data --max-age-hours 48

The JSON output includes each dataset status, resume cursor, coverage cell
count, and low-score cell count so it can be forwarded to normal log alerts.

The importer currently accepts UTF-8 or CP949 CSV. Official file endpoints can
require an interactive browser session and CAPTCHA, so download the initial
snapshot manually from the official catalog when automated access is rejected.
Full snapshot files belong under `backend/data/raw/` and are ignored by Git.

## Evidence rules

`PlaceTagEvidence` stores observations; `PlaceTag` remains the materialized search
aggregate for backward compatibility.

Evidence must include:

- source and source reference;
- positive, negative, or neutral polarity;
- confidence;
- observed time and optional expiry;
- context such as weekday/weekend, time range, or party type;
- the original short evidence needed for review.

AI may extract a tag from permitted evidence but may not create ground truth from
the place name alone. Name and category rules create low-confidence candidates.

## Coverage score

Coverage is calculated per administrative code, category, and source:

    20 base points when active source records exist
    + 30 * normalized-place ratio
    + 20 * tagged-place ratio
    + 30 * evidence-place ratio

The score is operational, not a user-facing quality claim. It determines the
order of nationwide enrichment jobs:

1. areas with no active source records;
2. areas with the lowest normalization ratio;
3. areas with the lowest evidence ratio;
4. high-demand query/category cells with insufficient evidence;
5. stale cells.

## Next implementation stages

1. Add the full snapshot downloader/source manifest with explicit license metadata.
2. Convert EPSG:5174 coordinates or geocode addresses, then promote valid rows.
3. Match canonical places to Kakao IDs without making Kakao the owned registry.
4. Generate objective tag candidates from business type and official fields.
5. Add evidence extraction queues and aggregation into `PlaceTag`.
6. Build regional tag-demand dashboards from the collected anonymous events.
7. Connect `check_nationwide_data` non-zero exits and JSON output to deployment alerts.

Bulk storage or reuse of third-party map/search content must be reviewed against
the provider's current terms before enabling that source in production.

## Kakao ID normalization

`SourcePlaceRecord` keeps the provider's original record ID. The final searchable
identity is a `Place(source="kakao_local", external_id=<Kakao place ID>)` only
when a match is confirmed from multiple signals. The matcher scores normalized
name, road/lot address, coordinate distance, phone, Kakao category, and franchise
branch identity. A place-name substring alone is never enough to link a record.

Run a small quota-bounded batch first:

    python manage.py match_source_places_to_kakao \
        --source localdata --after-id 0 --limit 100 \
        --max-api-requests 150 --batch-size 50

The command stores `confirmed`, `ambiguous`, `unmatched`, or `error` in
`KakaoPlaceMatch`. Only `confirmed` changes `SourcePlaceRecord.normalized_place`.
`KakaoPlaceSearchCache` caches each query for 30 days by default. Resume from the
reported `last_id`, retry selected outcomes with `--match-statuses ambiguous,error`,
and use `--refresh-cache` only when stale Kakao results must be fetched again.

Useful safety options:

- `--dry-run`: score candidates without writing matches or canonical places;
- `--max-api-requests`: stop before exceeding the planned quota;
- `--max-queries`: cap query variants per source row;
- `--confirmed-score` and `--min-margin`: keep weak or close candidates out of
  automatic linking.

## Nationwide library standard adapter

Download the merged CSV from the official
[`전국도서관표준데이터`](https://www.data.go.kr/data/15013109/standard.do) page,
then stage it without inventing map IDs:

    python manage.py import_library_standard_data C:\data\전국도서관표준데이터.csv
    python manage.py match_source_places_to_kakao \
        --source data_go_kr --dataset library_standard --max-api-requests 500
    python manage.py generate_library_meaningful_tags

The adapter stores library name/type, closure days, weekday/Saturday/holiday
hours, seats, address, operator, phone, homepage, coordinates, and reference
date in `SourcePlaceRecord`. After Kakao matching, only official-field facts are
confirmed: weekday closing at or after 21:00 (`야간운영`), valid Saturday or
holiday hours, and at least 100 reading seats by default. `도서관` remains the
category. Outlet availability, Wi-Fi, and laptop suitability are never inferred
from this standard dataset.

## Bookstore and SEMAS registry

No independently downloadable, clearly reusable nationwide bookstore registry
was identified. `서점ON` is useful for discovery and industry services, but its
complete store list is not exposed here as an open nationwide dataset. The
official SEMAS quarterly commercial-store snapshot is therefore the primary
bookstore registry and also a supplemental cafe/restaurant registry:

- file catalog: https://www.data.go.kr/data/15083033/fileData.do
- API catalog: https://www.data.go.kr/data/15012005/openapi.do

Use the CSV for the initial nationwide load:

    python manage.py import_semas_stores C:\data\소상공인_상가정보.csv \
        --snapshot-date 2026-03-31 \
        --categories cafe,restaurant,bookstore

The importer keeps `상가업소번호` only as `SourcePlaceRecord.source_record_id`,
stores the three-level and KSIC industry classifications in `raw`, and treats
them as place categories/search filters rather than meaningful tags. It skips
unrelated industries and then uses the same Kakao matching command with
`--source semas --dataset commercial_store`. The source warns that store IDs can
change when its classification system is rebuilt, so each quarterly snapshot
must be rematched rather than assumed to preserve historical identity.
