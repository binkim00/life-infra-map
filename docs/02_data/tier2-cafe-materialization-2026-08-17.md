# Tier 2 SEMAS cafe materialization — 2026-08-17

The existing SEMAS `commercial_store` registry was materialized with the same
conservative rules used for Seoul and Busan. Only source rows whose minor
business type is exactly `카페` were accepted. Study cafes, bakery-only rows and
other inferred cafe-like businesses were rejected. Ambiguous duplicates were
not merged and no Place was deleted.

The 2026 source combines Gwangju and Jeonnam under
`전남광주통합특별시`. Records in Gwangju's five autonomous districts are now
selected as `광주광역시`, and only their canonical address prefix is changed;
the original source value remains in `raw.source_sido_name`.

| Region | Before | Source candidates | New Place | After |
|---|---:|---:|---:|---:|
| Incheon | 1 | 6,369 | 5,646 | 5,647 |
| Daegu | 6 | 6,065 | 5,409 | 5,415 |
| Daejeon | 2 | 4,220 | 3,794 | 3,796 |
| Gwangju | 0 | 3,846 | 3,391 | 3,391 |
| Ulsan | 2 | 2,790 | 2,521 | 2,523 |

Across the five regions, 20,761 Places were created. 222 additional source rows
were linked to an existing/newly-created exact Place, 2,193 non-eligible rows
were rejected, and 101 ambiguous records remain unlinked. Materialization ran
in 10, 100, 1,000 and remaining-record stages.

No subjective Tag was inferred from the SEMAS category. The new Places enter
the existing Candidate-first enrichment planner; FeatureDocuments are generated
only after qualifying Tag/Evidence exists.
