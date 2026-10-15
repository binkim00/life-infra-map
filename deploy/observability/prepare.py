"""Generate private runtime configuration without printing credentials or raw logs."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--bind-ip", default="127.0.0.1")
    args = parser.parse_args()
    assert args.bind_ip == "127.0.0.1" or args.bind_ip.startswith("100.")
    root = Path(__file__).resolve().parent
    data = Path("/home/ubuntu/life-infra-map/runtime/observability-data")
    images = json.loads(args.images.read_text())
    names = ["life-infra-map-tag-worker", "life-infra-map-tag-scheduler", "life-infra-map-gateway", "life-infra-map-django-api", "life-infra-map-spring-api"]
    containers = json.loads(subprocess.check_output(["docker", "inspect", *names], text=True))
    targets = []
    for container in containers:
        path = container["LogPath"]
        assert path.startswith("/var/lib/docker/containers/") and path.endswith("-json.log")
        targets.append({"__path__": path.replace("/var/lib/docker/containers", "/docker-logs", 1), "service": container["Name"].removeprefix("/life-infra-map-"), "environment": "production"})
    for name, uid in [("loki", 10001), ("grafana", 472), ("alloy", 0)]:
        path = data / name
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, uid, uid)
        path.chmod(0o750)
    secret_dir = root / "secrets"
    secret_dir.mkdir(mode=0o700, exist_ok=True)
    # Grafana's uid must traverse the secret directory and read its own file.
    os.chown(secret_dir, 472, 472)
    password = secret_dir / "grafana-admin"
    if not password.exists():
        password.write_text(secrets.token_urlsafe(32))
        os.chown(password, 472, 472)
        password.chmod(0o600)
    env = root / ".env"
    env.write_text("\n".join([
        "GRAFANA_IMAGE=" + images["grafana/grafana:latest"]["digest"],
        "LOKI_IMAGE=" + images["grafana/loki:latest"]["digest"],
        "ALLOY_IMAGE=" + images["grafana/alloy:latest"]["digest"],
        "OBS_DATA_DIR=" + str(data), "GRAFANA_BIND_IP=" + args.bind_ip,
    ]) + "\n")
    env.chmod(0o600)
    target_literal = "[\n" + ",\n".join("{" + ", ".join(json.dumps(k) + " = " + json.dumps(v) for k, v in t.items()) + "}" for t in targets) + ",\n]"
    safe_fields = "{component: component, recorded_at: recorded_at, status: status, requests: requests, evidences: evidences, new_evidences: new_evidences, queue_depth: queue_depth, scanned: scanned, unique_candidates: unique_candidates, elapsed_ms: elapsed_ms, processing_ms: timings_ms.processing_ms}"
    alloy = '''local.file_match "app" {
  path_targets = TARGETS
}
loki.source.file "app" {
  targets = local.file_match.app.targets
  forward_to = [loki.process.safe.receiver]
}
loki.process "safe" {
  forward_to = [loki.write.local.receiver]
  stage.docker {}
  stage.match {
    selector = "{service=~\\"tag-worker|tag-scheduler\\"} !~ \\"^collection_metrics \\""
    action = "drop"
    drop_counter_reason = "non_numeric_collection"
  }
  stage.match {
    selector = "{service=~\\"tag-worker|tag-scheduler\\"}"
    stage.regex { expression = "^collection_metrics (?P<payload>.*)" }
    stage.output { source = "payload" }
    stage.json {
      expressions = { safe = SAFE_FIELDS }
      drop_malformed = true
    }
    stage.output { source = "safe" }
  }
  stage.match {
    selector = "{service=~\\"gateway|django-api\\"}"
    stage.regex {
      expression = "\\\"(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) [^\\\"]+\\\" (?P<status>[0-9]{3})"
    }
    stage.drop {
      source = "method"
      expression = "^$"
      drop_counter_reason = "unparsed_http"
    }
    stage.template {
      source = "safe"
      template = "{\\\"method\\\":\\\"{{ .method }}\\\",\\\"status\\\":\\\"{{ .status }}\\\"}"
    }
    stage.output { source = "safe" }
  }
  stage.match {
    selector = "{service=\\"spring-api\\"}"
    stage.regex { expression = "(?P<level>INFO|WARN|ERROR|DEBUG)" }
    stage.drop {
      source = "level"
      expression = "^$"
      drop_counter_reason = "unparsed_spring"
    }
    stage.template {
      source = "safe"
      template = "{\\\"level\\\":\\\"{{ .level }}\\\"}"
    }
    stage.output { source = "safe" }
  }
  stage.label_drop { values = ["filename"] }
}
loki.write "local" {
  endpoint { url = "http://loki:3100/loki/api/v1/push" }
}
'''
    alloy = alloy.replace("TARGETS", target_literal).replace("SAFE_FIELDS", json.dumps(safe_fields))
    (root / "config.alloy").write_text(alloy)
    for folder in ["datasources", "dashboards"]:
        (root / "provisioning" / folder).mkdir(parents=True, exist_ok=True)
    datasource = {"apiVersion": 1, "datasources": [{"name": "LifeMap Loki", "uid": "lifemap-loki", "type": "loki", "access": "proxy", "url": "http://loki:3100", "isDefault": True, "editable": False}]}
    (root / "provisioning/datasources/loki.yaml").write_text(json.dumps(datasource))
    dashboard = {"uid": "lifemap-logs", "title": "LifeMap 서비스 로그", "schemaVersion": 39, "version": 1, "refresh": "30s", "time": {"from": "now-1h", "to": "now"}, "panels": [{"id": 1, "title": "정제된 서비스 로그", "type": "logs", "gridPos": {"x": 0, "y": 0, "w": 24, "h": 18}, "datasource": {"type": "loki", "uid": "lifemap-loki"}, "targets": [{"refId": "A", "expr": '{environment="production"}', "queryType": "range"}]}]}
    (root / "provisioning/dashboards/lifemap.json").write_text(json.dumps(dashboard, ensure_ascii=False))
    provider = {"apiVersion": 1, "providers": [{"name": "LifeMap", "type": "file", "options": {"path": "/etc/grafana/provisioning/dashboards"}}]}
    (root / "provisioning/dashboards/provider.yaml").write_text(json.dumps(provider))
    print(json.dumps({"targets": len(targets), "bind_ip": args.bind_ip, "credentials_printed": False}))


if __name__ == "__main__":
    main()
