# Official place-source load — 2026-08-15

This is the reproducibility record for the PostgreSQL development baseline.
Raw files remain under the gitignored `backend/data/raw/` directory; only their
provenance, checksums, and resulting database counts are committed.

## Nationwide library standard data

- Catalog: https://www.data.go.kr/data/15013109/standard.do
- Portal snapshot date: 2026-07-24
- Downloaded rows: 3,554
- Local UTF-8 CSV size: 1,412,665 bytes
- SHA-256: `6ac37c2c094540ca93b718bcf4da2f75ccb5672c21aceed639c54416a16fb5a1`
- Stored `SourcePlaceRecord` rows: 3,526
- Duplicate/update rows in the official merge: 28

The load preserves the official fields and creates no place identity by itself.
Kakao normalization remains a separate step. Library hours and seat counts may
later produce official-field evidence; library category, outlets, Wi-Fi, and
laptop suitability are not inferred as meaningful tags.

## SEMAS commercial-store data

- Catalog: https://www.data.go.kr/data/15083033/fileData.do
- Snapshot: 2026-06-30 (2026 Q2)
- ZIP size: 352,699,739 bytes
- SHA-256: `57aa361544108ff4fc73334f87d2ced61e41fe8638dd70bcd842930f865d2386`
- Regional CSV files: 16, 2,772,484 source rows read
- Stored rows after category filtering: 858,105
  - restaurant: 717,310
  - cafe: 134,033
  - bookstore: 6,762

`상가업소번호` is preserved as the source record ID. Industry classifications
remain category/search-filter metadata and do not create meaningful tags.

The 2026 Q2 source represents the former Gwangju and Jeonnam area as
`전남광주통합특별시`, so this source snapshot has 16 first-level regions. The
staging adapter derives Gwangju from its five autonomous districts and treats
the remaining combined rows as Jeonnam for the service's 17-region strata. The
original source label is retained in `raw.source_sido_name`.

## Validation

- PostgreSQL/PostGIS was used for both loads.
- Importer tests and nationwide import regression tests passed (10 tests).
- The UTF-8 detector now accepts a valid multibyte character split exactly at
  the 64 KiB sampling boundary, which occurred in an official regional CSV.
- Current aggregate inventory is recorded in `docs/02_data/place-inventory.json`.
