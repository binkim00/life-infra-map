# Daily launch quality report

This timer runs after the daily Codex evidence collection and measures the
Busan launch cohort against 24 cafe and restaurant feature queries. It writes
coverage, full evaluation output, and a compact release-gate summary under
`/home/ubuntu/life-infra-map/runtime/quality-reports`.

The release gate remains closed unless every query returns five results, every
query has at least one verified feature match in its top five, at least 60% of
all top-five results have a verified feature match, reasons are transparent,
and no hard violation is present.

Install or update:

```bash
chmod 0755 deploy/quality-report/run-quality-report.sh
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
