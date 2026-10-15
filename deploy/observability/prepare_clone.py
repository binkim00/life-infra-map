"""Prepare an explicitly mounted, offline LifeMap root volume for first boot.

Never run against / or the production volume. Preserve DB files and backup data.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--old-private-ip", required=True)
    parser.add_argument("--new-private-ip", required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    assert root != Path("/") and root.is_mount(), "An offline mounted clone is required"
    old_ip = str(ipaddress.IPv4Address(args.old_private_ip))
    new_ip = str(ipaddress.IPv4Address(args.new_private_ip))
    assert old_ip != new_ip

    def inside(relative):
        path = root / relative
        assert path.resolve(strict=False).is_relative_to(root), "Path escapes clone"
        return path

    home = inside("home/ubuntu/life-infra-map")
    inventory = json.loads((home / "runtime/observability-20261015/source-preflight.json").read_text())
    containers = inventory["containers"]
    assert len(containers) == 9
    control_dir = home / "runtime/migration-20261015"
    control_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    control = control_dir / "clone-control.json"
    assert not control.exists(), "Clone was already prepared; inspect saved control first"
    enabled = []
    for directory in inside("etc/systemd/system").glob("*.wants"):
        if not directory.is_dir():
            continue
        for link in directory.iterdir():
            if link.name.startswith("life-infra-map-") and link.name.endswith(".timer"):
                assert link.is_symlink(), "Unexpected regular timer entry"
                enabled.append({"relative": str(link.relative_to(root)), "target": os.readlink(link)})
    # Persist the recovery recipe before modifying clone-only configuration.
    plan = {"old_private_ip": old_ip, "new_private_ip": new_ip,
            "containers": [{"id": c["id"], "name": c["name"], "image": c["image"],
                            "restart_policy": c["restart_policy"]} for c in containers],
            "enabled_timer_links": enabled, "application_autostart_held": True}
    control.write_text(json.dumps(plan))
    control.chmod(0o600)

    caddy = home / "app/deploy/public-edge/Caddyfile"
    contents = caddy.read_text()
    assert "bind " + old_ip in contents
    caddy.write_text(contents.replace("bind " + old_ip, "bind " + new_ip))
    for c in containers:
        directory = inside("var/lib/docker/containers") / c["id"]
        host_file = directory / "hostconfig.json"
        config_file = directory / "config.v2.json"
        host = json.loads(host_file.read_text())
        config = json.loads(config_file.read_text())
        assert config["Name"] == c["name"] and config["Image"] == c["image"]
        host["RestartPolicy"] = {"Name": "no", "MaximumRetryCount": 0}
        for bindings in (host.get("PortBindings") or {}).values():
            for binding in bindings or []:
                if binding.get("HostIp") == old_ip:
                    binding["HostIp"] = new_ip
        values = config.get("Config", {}).get("Env", [])
        for index, value in enumerate(values):
            if value == "TRUSTED_EDGE_IP=" + old_ip:
                values[index] = "TRUSTED_EDGE_IP=" + new_ip
        host_file.write_text(json.dumps(host))
        config_file.write_text(json.dumps(config))
    for entry in enabled:
        # Absolute unit symlink targets refer to the clone's future root.
        # Validate the parent, then unlink only the recorded symlink itself.
        link = root / entry["relative"]
        assert link.parent.resolve(strict=True).is_relative_to(root)
        assert link.is_symlink()
        assert os.readlink(link) == entry["target"]
        link.unlink()
    # Only private bind addresses in known deployment envs; never print contents.
    for prefix in [home / "deploy", home / "app/deploy"]:
        for component in ["api", "spring-api", "gateway", "storage", "db"]:
            env = prefix / component / ".env"
            if env.is_file():
                original = env.read_text()
                env.write_text(original.replace("=" + old_ip + "\n", "=" + new_ip + "\n"))
    subprocess.run(["sync"], check=True)
    print(json.dumps({"containers_held": len(containers), "timers_held": len(enabled),
                      "private_bind_updated": True, "db_and_backup_files_modified": False}))


if __name__ == "__main__":
    main()
