"""Package an explicit, reviewed set of tracked files from one immutable commit."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

ALLOWED = (
    "backend/", "spring-api/", "frontend/",
    "deploy/api/", "deploy/spring-api/", "deploy/gateway/", "deploy/public-edge/",
)
FORBIDDEN_PARTS = {"node_modules", ".git", ".env", "secrets", "credentials"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
SHA_RE = re.compile(r"[0-9a-f]{40}")


def git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if result.returncode:
        raise ValueError("Git could not read the requested commit or file")
    return result.stdout


def validate_path(raw: str) -> str:
    path = PurePosixPath(raw.replace("\\", "/"))
    value = path.as_posix()
    if (
        path.is_absolute() or ".." in path.parts or not value.startswith(ALLOWED)
        or any(part.lower() in FORBIDDEN_PARTS for part in path.parts)
        or any(part.lower().startswith(".env") for part in path.parts)
        or path.suffix.lower() in FORBIDDEN_SUFFIXES
    ):
        raise ValueError(f"Path is not allowed for release: {raw}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True, help="40-character tested commit SHA")
    parser.add_argument("--ci-run", required=True, help="Successful GitHub Actions run number")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--file", action="append", required=True, dest="files")
    args = parser.parse_args()

    if not SHA_RE.fullmatch(args.commit):
        parser.error("--commit must be a full 40-character lowercase SHA")
    if not args.ci_run.isdecimal() or int(args.ci_run) < 1:
        parser.error("--ci-run must be a positive run number")
    files = [validate_path(item) for item in args.files]
    if len(files) != len(set(files)):
        parser.error("Duplicate --file paths are not allowed")
    resolved = git("rev-parse", "--verify", f"{args.commit}^{{commit}}").decode().strip()
    if resolved != args.commit:
        parser.error("The requested commit did not resolve exactly")

    entries = []
    content = {}
    for path in sorted(files):
        kind = git("cat-file", "-t", f"{args.commit}:{path}").decode().strip()
        if kind != "blob":
            parser.error(f"Not a tracked file at the commit: {path}")
        data = git("show", f"{args.commit}:{path}")
        content[path] = data
        entries.append({
            "path": path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        })

    manifest = {
        "repository": "binkim00/life-infra-map",
        "commit": args.commit,
        "ci_run": int(args.ci_run),
        "files": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("Output already exists; choose a new release name")
    try:
        with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, data in content.items():
                archive.writestr(path, data)
            archive.writestr("release-manifest.json", json.dumps(
                manifest, ensure_ascii=False, indent=2
            ).encode("utf-8"))
    except Exception:
        args.output.unlink(missing_ok=True)
        raise
    print(json.dumps({
        "archive": str(args.output),
        "archive_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "commit": args.commit,
        "ci_run": int(args.ci_run),
        "file_count": len(entries),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as error:
        print(error, file=sys.stderr)
        sys.exit(2)
