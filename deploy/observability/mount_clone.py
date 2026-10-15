"""Mount only the explicitly identified migration clone, prepare, and unmount."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--volume-id", required=True)
    args = parser.parse_args()
    assert args.volume_id.startswith("vol-")
    assert args.volume_id not in {"vol-034c6c2614d6c2d12", "vol-08dba8c63e6b6ee9b"}
    devices = json.loads(subprocess.check_output(
        ["lsblk", "-J", "-p", "-o", "NAME,SERIAL,FSTYPE,MOUNTPOINTS"], text=True
    ))["blockdevices"]
    matches = [d for d in devices if d.get("serial") == args.volume_id.replace("-", "")]
    assert len(matches) == 1, "Exactly one clone NVMe volume must match"
    disk = matches[0]
    partitions = disk.get("children", [])
    assert all(not any(p.get("mountpoints") or []) for p in partitions), "Clone already mounted"
    roots = [p for p in partitions if p["name"].endswith("p1") and p["fstype"] == "ext4"]
    assert len(roots) == 1
    mount = Path("/mnt/lifemap-final-clone")
    mount.mkdir(mode=0o700, exist_ok=True)
    assert not mount.is_mount() and not any(mount.iterdir())
    subprocess.run(["mount", roots[0]["name"], str(mount)], check=True)
    try:
        home = mount / "home/ubuntu/life-infra-map"
        frozen = home / "runtime/observability-20261015/source-frozen-counts.json"
        assert json.loads(frozen.read_text())["table_count"] == 51
        source = Path(__file__).resolve().parent
        target = home / "app/deploy/observability"
        target.mkdir(parents=True, exist_ok=True)
        for name in ["compose.json", "loki.json", "prepare.py", "prepare_clone.py",
                     "db_fingerprint.py", "README.md", "MIGRATION.md", ".gitignore"]:
            shutil.copy2(source / name, target / name)
        subprocess.run(["python3", str(source / "prepare_clone.py"), "--root", str(mount),
                        "--old-private-ip", "172.31.32.178",
                        "--new-private-ip", "172.31.23.232"], check=True)
        runtime = home / "runtime/migration-20261015"
        shutil.copy2(Path("/home/ubuntu/life-infra-map/runtime/migration-20261015/monitoring-images.json"),
                     runtime / "monitoring-images.json")
        # Preserve config files and report only interface constraints, never secret values.
        netplan = []
        for path in (mount / "etc/netplan").glob("*.yaml"):
            contents = path.read_text()
            netplan.append({"file": path.name, "mac_match": "macaddress:" in contents,
                            "old_private_ip": "172.31.32.178" in contents})
        assert not any(x["mac_match"] or x["old_private_ip"] for x in netplan), \
            "Review clone network config before boot"
        record = {"clone_volume_id": args.volume_id, "frozen_table_count": 51,
                  "netplan": netplan, "prepared": True}
        (runtime / "offline-preparation.json").write_text(json.dumps(record))
        subprocess.run(["sync"], check=True)
        print(json.dumps(record))
    finally:
        subprocess.run(["umount", str(mount)], check=True)


if __name__ == "__main__":
    main()
