import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import disk_guard


class DiskGuardTests(unittest.TestCase):
    def test_severity_checks_usage_and_free_bytes(self):
        snapshot = {"used_percent": 70, "free_bytes": 6 * disk_guard.GIB}
        self.assertEqual(disk_guard.severity(snapshot), "normal")
        snapshot["used_percent"] = 83
        self.assertEqual(disk_guard.severity(snapshot), "warning")
        snapshot["free_bytes"] = disk_guard.GIB
        self.assertEqual(disk_guard.severity(snapshot), "critical")

    def test_alerts_only_on_level_change_and_records_history(self):
        snapshot = {
            "at": "2026-09-28T06:00:00+00:00",
            "total_bytes": 30 * disk_guard.GIB,
            "used_bytes": 25 * disk_guard.GIB,
            "free_bytes": 5 * disk_guard.GIB,
            "used_percent": 83.3,
        }
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(disk_guard, "STATE_DIR", Path(directory)),
                patch.object(disk_guard, "disk_snapshot", return_value=snapshot),
                patch.object(disk_guard, "publish_alert") as publish,
            ):
                disk_guard.monitor(False)
                disk_guard.monitor(False)
                self.assertEqual(publish.call_count, 1)
                self.assertEqual(publish.call_args.args[0], "warning")
                history = (Path(directory) / "history.jsonl").read_text().splitlines()
                self.assertEqual(len(history), 2)
                self.assertEqual(json.loads(history[-1])["level"], "warning")

    def test_dry_run_does_not_send_or_write(self):
        snapshot = {
            "at": "2026-09-28T06:00:00+00:00",
            "total_bytes": 30 * disk_guard.GIB,
            "used_bytes": 27 * disk_guard.GIB,
            "free_bytes": 3 * disk_guard.GIB,
            "used_percent": 90.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(disk_guard, "STATE_DIR", Path(directory)),
                patch.object(disk_guard, "disk_snapshot", return_value=snapshot),
                patch.object(disk_guard, "publish_alert") as publish,
            ):
                disk_guard.monitor(True)
                publish.assert_not_called()
                self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
