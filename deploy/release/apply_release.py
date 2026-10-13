"""Validate and apply a reviewed release ZIP to a non-Git server checkout."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ALLOWED = (
    "backend/", "spring-api/", "frontend/",
    "deploy/api/", "deploy/spring-api/", "deploy/gateway/", "deploy/public-edge/",
)
FORBIDDEN_PARTS = {"node_modules", ".git", ".env", "secrets", "credentials"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if (
        path.is_absolute() or ".." in path.parts or not name.startswith(ALLOWED)
        or any(p.lower() in FORBIDDEN_PARTS or p.lower().startswith(".env") for p in path.parts)
        or path.suffix.lower() in FORBIDDEN_SUFFIXES
    ):
        raise ValueError(f"Unsafe release path: {name}")
    target = root
    for part in path.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError(f"Symlink in release path: {name}")
    return target


def read_archive(archive_path: Path, root: Path):
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "release-manifest.json" not in names:
            raise ValueError("Invalid archive entries")
        manifest = json.loads(archive.read("release-manifest.json"))
        entries = manifest.get("files")
        if manifest.get("repository") != "binkim00/life-infra-map" or not isinstance(entries, list) or not entries:
            raise ValueError("Invalid release manifest")
        expected = {item["path"] for item in entries}
        if len(expected) != len(entries) or set(names) != expected | {"release-manifest.json"}:
            raise ValueError("Archive and manifest paths differ")
        content = {}
        for item in entries:
            name = item["path"]
            safe_path(root, name)
            data = archive.read(name)
            if len(data) != item["size"] or sha256(data) != item["sha256"]:
                raise ValueError(f"Hash mismatch: {name}")
            content[name] = data
    return manifest, content


def atomic_write(target: Path, data: bytes, mode: int = 0o644):
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".release-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply(args):
    root = args.root.resolve(strict=True)
    manifest, content = read_archive(args.archive, root)
    summary = {
        "commit": manifest["commit"],
        "ci_run": manifest["ci_run"],
        "archive_sha256": sha256(args.archive.read_bytes()),
        "files": [],
    }
    for name, data in content.items():
        target = safe_path(root, name)
        before = target.read_bytes() if target.exists() else None
        summary["files"].append({
            "path": name,
            "before_sha256": sha256(before) if before is not None else None,
            "after_sha256": sha256(data),
            "changed": before != data,
        })
    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    backup = args.backup.resolve()
    if backup == root or root in backup.parents:
        raise ValueError("Backup must be outside the app root")
    if backup.exists():
        raise ValueError("Backup directory already exists")
    backup.mkdir(parents=True, mode=0o700)
    receipt = {**summary, "root": str(root), "status": "prepared"}
    changed = []
    try:
        for entry in summary["files"]:
            if not entry["changed"]:
                continue
            target = safe_path(root, entry["path"])
            if target.exists():
                saved = backup / "originals" / entry["path"]
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
        atomic_write(backup / "receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2).encode())
        for entry in summary["files"]:
            if not entry["changed"]:
                continue
            target = safe_path(root, entry["path"])
            mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
            atomic_write(target, content[entry["path"]], mode)
            changed.append(entry)
        receipt["status"] = "applied"
        atomic_write(backup / "receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2).encode())
    except Exception:
        for entry in reversed(changed):
            target = safe_path(root, entry["path"])
            saved = backup / "originals" / entry["path"]
            if saved.exists():
                shutil.copy2(saved, target)
            else:
                target.unlink(missing_ok=True)
        receipt["status"] = "failed_and_restored"
        atomic_write(backup / "receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2).encode())
        raise
    print(json.dumps({"backup": str(backup), "status": receipt["status"], "changed": len(changed)}))


def rollback(args):
    root = args.root.resolve(strict=True)
    backup = args.backup.resolve(strict=True)
    if backup == root or root in backup.parents:
        raise ValueError("Backup must be outside the app root")
    receipt = json.loads((backup / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("status") != "applied" or receipt.get("root") != str(root):
        raise ValueError("Receipt is not an applied release for this root")
    for entry in receipt["files"]:
        if not entry["changed"]:
            continue
        target = safe_path(root, entry["path"])
        if not target.exists() or sha256(target.read_bytes()) != entry["after_sha256"]:
            raise ValueError(f"Current file changed since release: {entry['path']}")
        saved = backup / "originals" / entry["path"]
        if entry["before_sha256"] is not None and (
            not saved.exists() or sha256(saved.read_bytes()) != entry["before_sha256"]
        ):
            raise ValueError(f"Backup file mismatch: {entry['path']}")
    for entry in receipt["files"]:
        if not entry["changed"]:
            continue
        target = safe_path(root, entry["path"])
        saved = backup / "originals" / entry["path"]
        if saved.exists():
            atomic_write(target, saved.read_bytes(), saved.stat().st_mode & 0o777)
        else:
            target.unlink()
    receipt["status"] = "rolled_back"
    atomic_write(backup / "receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2).encode())
    print(json.dumps({"status": "rolled_back", "backup": str(backup)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if not args.backup or (not args.rollback and not args.archive):
        parser.error("--backup and, unless rolling back, --archive are required")
    if args.rollback and args.apply:
        parser.error("--rollback and --apply are mutually exclusive")
    if args.rollback:
        rollback(args)
    else:
        apply(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"Release failed: {error}", file=sys.stderr)
        sys.exit(2)
