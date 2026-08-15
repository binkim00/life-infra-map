# Nationwide subjective-tag sample — 2026-08-15

The sample builder was run with five places per available first-level-region and
category cell. Only a direct `kakao_local` place or a `KakaoPlaceMatch` with
`status=confirmed` is eligible.

## Queue result

- First-level regions represented: 17/17
- Target cells: 68 (17 regions × 4 categories)
- Covered cells: 52
- Distinct queued places: 187
- Queue requests: 1,351
- Category coverage:
  - cafe: 17/17 regions
  - restaurant: 17/17 regions
  - city park: 17/17 regions
  - tourism: 1/17 regions

The 16 missing tourism cells were not filled with unverified public IDs. Legacy
TourAPI places were staged as `SourcePlaceRecord` rows, but the first live
85-place normalization batch produced no automatic confirmations under the
name/address/coordinate threshold. This is retained as an explicit coverage gap
for later matching rather than weakening the identity rule.

## Matching used for the sample

- Nationwide SEMAS validation rows attempted: 530
- SEMAS confirmed matches: 90
- Cafe/restaurant confirmed cells: 34/34
- Matcher cache and API ceilings remained enabled.
- A false branch-conflict case caused only by spacing differences was fixed and
  re-evaluated from cache; genuinely different branch names remain blocked.

`TAG_ENRICHMENT_ENABLED` remains false. Creating this queue does not start Naver
collection; evidence processing is enabled only after review tooling and the
selected batch are ready.
