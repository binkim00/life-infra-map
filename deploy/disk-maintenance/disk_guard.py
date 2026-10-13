#!/usr/bin/env python3
"""Monitor root disk usage and prune only old, disposable Docker build cache."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


STATE_DIR = Path(
    os.environ.get(
        "DISK_GUARD_STATE_DIR", "/home/ubuntu/life-infra-map/runtime/disk-maintenance"
    )
)
TOPIC_ARN = os.environ.get("DISK_GUARD_SNS_TOPIC_ARN", "")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
GIB = 1024**3


def disk_snapshot() -> dict:
    usage = shutil.disk_usage("/")
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round(100 * usage.used / usage.total, 1),
    }


def severity(snapshot: dict) -> str:
    if snapshot["used_percent"] >= 90 or snapshot["free_bytes"] < 2 * GIB:
        return "critical"
    if snapshot["used_percent"] >= 80 or snapshot["free_bytes"] < 5 * GIB:
        return "warning"
    return "normal"


def read_state() -> dict:
    path = STATE_DIR / "state.json"
    if not path.exists():
        return {"level": "normal"}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(state: dict) -> None:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = STATE_DIR / "state.json.tmp"
    temporary.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(STATE_DIR / "state.json")


def write_history(snapshot: dict, level: str) -> None:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = STATE_DIR / "history.jsonl"
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    records = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if datetime.fromisoformat(record["at"]) >= cutoff:
                records.append(record)
    records.append({**snapshot, "level": level})
    temporary = STATE_DIR / "history.jsonl.tmp"
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(path)


def publish_alert(level: str, snapshot: dict) -> None:
    if not TOPIC_ARN:
        raise RuntimeError("DISK_GUARD_SNS_TOPIC_ARN is required for alerts")
    import boto3

    label = {"warning": "주의", "critical": "긴급", "normal": "회복"}[level]
    message = (
        f"서버: {socket.gethostname()}\n"
        f"루트 디스크: {snapshot['used_percent']}% 사용, "
        f"{snapshot['free_bytes'] / GIB:.1f} GiB 남음\n"
        f"측정 시각: {snapshot['at']}\n"
        "서비스: life-infra-map-disk-monitor.service\n"
        "DB 볼륨과 롤백 이미지/백업은 자동 삭제하지 않습니다.\n"
        "디스크 사용 추세를 확인하고 필요하면 EBS 증설을 검토하세요."
    )
    boto3.client("sns", region_name=REGION).publish(
        TopicArn=TOPIC_ARN,
        Subject=f"[여기일지도] 서버 디스크 {label}",
        Message=message,
    )


def monitor(dry_run: bool) -> None:
    snapshot = disk_snapshot()
    level = severity(snapshot)
    previous = read_state().get("level", "normal")
    event = {**snapshot, "level": level, "previous_level": previous}
    if dry_run:
        print(json.dumps({**event, "dry_run": True}, ensure_ascii=False))
        return
    if level != previous:
        publish_alert(level, snapshot)
    write_history(snapshot, level)
    write_state({"level": level, "at": snapshot["at"]})
    print(json.dumps(event, ensure_ascii=False))


def cleanup() -> None:
    before = disk_snapshot()
    result = subprocess.run(
        [
            "docker", "builder", "prune", "--force", "--filter", "until=168h",
            "--keep-storage", "2GB",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    after = disk_snapshot()
    summary = next(
        (line for line in result.stdout.splitlines() if line.startswith("Total reclaimed space:")),
        "Total reclaimed space: unknown",
    )
    print(json.dumps({
        "at": after["at"],
        "operation": "old_build_cache_only",
        "summary": summary,
        "free_before_bytes": before["free_bytes"],
        "free_after_bytes": after["free_bytes"],
    }, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("monitor", "cleanup"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.mode == "monitor":
        monitor(args.dry_run)
    elif args.dry_run:
        parser.error("cleanup has no dry-run mode")
    else:
        cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
