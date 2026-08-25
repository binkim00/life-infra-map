# Daily launch quality report

This timer runs after the daily Codex evidence collection and measures the
Busan launch cohort against 24 cafe and restaurant feature queries. It writes
coverage, full evaluation output, prioritized collection feedback, and a compact release-gate summary under
`/home/ubuntu/life-infra-map/runtime/quality-reports`.
The coverage step uses a launch-only aggregate instead of the much heavier
cross-city, per-tag operations report.

The release gate remains closed unless every query returns five results, every
query has at least one verified feature match in its top five, at least 60% of
all top-five results have a verified feature match, reasons are transparent,
and no hard violation is present. The p95 response time must be at most three
seconds, and all criteria must hold for three consecutive daily reports before
`release_gate.ready` becomes true.

Each evaluation also converts the top-five results' missing verified conditions
into idempotent `TagEnrichmentRequest` rows. The next Codex evidence run consumes
these requests first. `daily_delta` reports searchable/rich place growth and
changes in the two feature-hit metrics compared with the previous report.

Install or update:

```bash
chmod 0755 deploy/quality-report/run-quality-report.sh
sudo install -d -o ubuntu -g ubuntu -m 0700 /home/ubuntu/life-infra-map/runtime/quality-reports
sudo install -m 0644 deploy/quality-report/life-infra-map-quality-report.service /etc/systemd/system/
sudo install -m 0644 deploy/quality-report/life-infra-map-quality-report.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now life-infra-map-quality-report.timer
```

Run and inspect:

```bash
sudo systemctl start life-infra-map-quality-report.service
sudo systemctl status life-infra-map-quality-report.service
jq . /home/ubuntu/life-infra-map/runtime/quality-reports/latest-summary.json
```
