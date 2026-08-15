# Evidence promotion validation — 2026-08-15

The active evidence aggregate was evaluated in dry-run mode and then
materialized against PostgreSQL.

## Current live-data result

- Place/tag evidence pairs evaluated: 24
- Candidate pairs: 7
- Rejected pairs: 0
- Confirmed pairs: 0
- Pairs with no active evidence after expiry: 17
- Web-only candidate confidence ceiling: 75

No web-only observation was promoted to confirmed. The active candidates remain
`is_verified=false`; historical evidence stays auditable but does not contribute
after its expiry date.

## Promotion policy verified by tests

- one official positive field can confirm when no active official negative
  evidence conflicts;
- three independent web URLs raise candidate confidence but never auto-confirm;
- three independent positive web URLs plus net-positive explicit user feedback
  can confirm;
- one or more positive web URLs plus net-positive administrator review can
  confirm;
- active negative evidence reduces or blocks promotion;
- an active official negative blocks a simultaneous official positive and
  materializes the tag as rejected;
- expiry removes confirmations created by the evidence aggregator, without
  deleting unrelated confirmations created by the independent user-interaction
  aggregation path.

This keeps source observations separate from the searchable materialization and
makes re-aggregation safe when evidence becomes stale.
