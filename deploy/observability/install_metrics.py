"""Add private host metrics without recreating existing containers or printing secrets."""
import base64
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error


ROOT = Path(__file__).resolve().parent
HOME = Path('/home/ubuntu/life-infra-map')
RUNTIME = HOME / 'runtime/host-metrics-20261015'


def run(args):
    return subprocess.check_output(args, text=True).strip()


def grafana(path, payload=None):
    password = (ROOT / 'secrets/grafana-admin').read_text().strip()
    token = base64.b64encode(('admin:' + password).encode()).decode()
    request = urllib.request.Request('http://100.71.169.91:3300' + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Basic ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    assert ROOT == HOME / 'app/deploy/observability', 'Run staged server file'
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    ids = run(['docker', 'ps', '-aq']).split()
    before = json.loads(run(['docker', 'inspect', *ids]))
    baseline_path = RUNTIME / 'before.json'
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        ids = list(baseline)
    else:
        baseline = {c['Id']: {'image': c['Image'], 'mounts': c['Mounts'],
                             'running': c['State']['Running']} for c in before}
        baseline_path.write_text(json.dumps(baseline))
    images = {}
    images_path = RUNTIME / 'images.json'
    if images_path.exists():
        images = json.loads(images_path.read_text())
    else:
        for repository, variable in [('prom/prometheus', 'PROMETHEUS_IMAGE'),
                                     ('prom/node-exporter', 'NODE_EXPORTER_IMAGE')]:
            subprocess.run(['docker', 'pull', '--quiet', repository + ':latest'], check=True,
                           stdout=subprocess.DEVNULL)
            digest = json.loads(run(['docker', 'image', 'inspect', repository + ':latest']))[0]['RepoDigests'][0]
            images[variable] = digest
        images_path.write_text(json.dumps(images))
    (ROOT / '.env.metrics').write_text(''.join(k + '=' + v + '\n' for k, v in images.items()))
    (ROOT / '.env.metrics').chmod(0o600)
    data = HOME / 'runtime/observability-data/prometheus'
    data.mkdir(parents=True, exist_ok=True)
    os.chown(data, 65534, 65534)
    config = {'global': {'scrape_interval': '30s', 'evaluation_interval': '30s'},
              'scrape_configs': [{'job_name': 'lifemap-host', 'scrape_timeout': '10s',
                  'sample_limit': 3000, 'static_configs': [{'targets': ['host.docker.internal:19100'],
                  'labels': {'environment': 'production', 'server': 'lifemap-c7'}}]}]}
    (ROOT / 'prometheus.json').write_text(json.dumps(config))
    compose = ['docker', 'compose', '--env-file', '.env', '--env-file', '.env.metrics',
               '-f', 'compose.json', '-f', 'compose.metrics.json']
    subprocess.run(compose + ['config', '--quiet'], cwd=ROOT, check=True)
    subprocess.run(compose + ['up', '-d', '--no-deps', 'prometheus', 'node-exporter'], cwd=ROOT, check=True)
    datasource = {'apiVersion': 1, 'datasources': [{'name': 'LifeMap Prometheus',
        'uid': 'lifemap-prometheus', 'type': 'prometheus', 'access': 'proxy',
        'url': 'http://prometheus:9090', 'isDefault': False, 'editable': False,
        'jsonData': {'timeInterval': '30s', 'httpMethod': 'POST'}}]}
    (ROOT / 'provisioning/datasources/prometheus.yaml').write_text(json.dumps(datasource))
    grafana('/api/admin/provisioning/datasources/reload', {})
    queries = [
        ('CPU 사용률', '100 * (1 - avg(rate(node_cpu_seconds_total{job="lifemap-host",mode="idle"}[2m])))', 'percent'),
        ('메모리 사용률', '100 * (1 - node_memory_MemAvailable_bytes{job="lifemap-host"} / node_memory_MemTotal_bytes{job="lifemap-host"})', 'percent'),
        ('루트 디스크 사용률', '100 * (1 - node_filesystem_avail_bytes{job="lifemap-host",mountpoint="/"} / node_filesystem_size_bytes{job="lifemap-host",mountpoint="/"})', 'percent'),
        ('디스크 남은 공간', 'node_filesystem_avail_bytes{job="lifemap-host",mountpoint="/"}', 'bytes'),
        ('스왑 사용량', 'node_memory_SwapTotal_bytes{job="lifemap-host"} - node_memory_SwapFree_bytes{job="lifemap-host"}', 'bytes'),
        ('네트워크 수신', 'rate(node_network_receive_bytes_total{job="lifemap-host",device!~"lo|veth.*|docker.*|br-.*"}[2m])', 'Bps'),
        ('네트워크 송신', 'rate(node_network_transmit_bytes_total{job="lifemap-host",device!~"lo|veth.*|docker.*|br-.*"}[2m])', 'Bps'),
        ('서버 부하', 'node_load1{job="lifemap-host"}', 'short'),
    ]
    panels = []
    for index, (title, query, unit) in enumerate(queries):
        panels.append({'id': index + 1, 'title': title, 'type': 'timeseries',
            'datasource': {'type': 'prometheus', 'uid': 'lifemap-prometheus'},
            'gridPos': {'x': (index % 2) * 12, 'y': (index // 2) * 8, 'w': 12, 'h': 8},
            'fieldConfig': {'defaults': {'unit': unit, 'min': 0}, 'overrides': []},
            'targets': [{'refId': 'A', 'expr': query,
                         'legendFormat': '{{device}}' if index in (5, 6) else title, 'range': True}]})
    dashboard = {'uid': 'lifemap-host', 'title': 'LifeMap 서버 자원', 'schemaVersion': 39,
        'version': 1, 'refresh': '30s', 'time': {'from': 'now-1h', 'to': 'now'},
        'description': '30초 간격으로 수집한 실제 호스트 자원. 설치 전 과거 데이터는 없습니다.',
        'panels': panels}
    (ROOT / 'provisioning/dashboards/host.json').write_text(json.dumps(dashboard, ensure_ascii=False))
    grafana('/api/admin/provisioning/dashboards/reload', {})
    # Wait for two scrapes so rate() panels have actual samples.
    metrics = {}
    for attempt in range(18):
        metrics = {}
        try:
            for title, query, _ in queries:
                path = '/api/datasources/proxy/uid/lifemap-prometheus/api/v1/query?' + urllib.parse.urlencode({'query': query})
                response = grafana(path)
                values = response['data']['result']
                assert response['status'] == 'success' and values
                metrics[title] = [v['value'][1] for v in values]
            break
        except urllib.error.HTTPError as error:
            if error.code not in (502, 503):
                raise
            time.sleep(10)
        except (AssertionError, KeyError, urllib.error.URLError):
            time.sleep(10)
    else:
        raise RuntimeError('Metrics incomplete; inspect scrape health')
    after = json.loads(run(['docker', 'inspect', *ids]))
    for c in after:
        original = baseline[c['Id']]
        assert original['image'] == c['Image'] and original['running'] == c['State']['Running']
        assert sorted(original['mounts'], key=lambda m: m['Destination']) == sorted(c['Mounts'], key=lambda m: m['Destination'])
        assert not c['State']['OOMKilled']
        assert c['State'].get('Health', {}).get('Status', 'healthy') == 'healthy'
    assert grafana('/api/datasources/uid/lifemap-prometheus/health')['status'] == 'OK'
    assert len(grafana('/api/dashboards/uid/lifemap-host')['dashboard']['panels']) == 8
    record = {'dashboard': 'lifemap-host', 'panels_with_actual_samples': metrics,
              'existing_containers_unchanged': len(ids), 'images': images}
    (RUNTIME / 'verification.json').write_text(json.dumps(record, ensure_ascii=False))
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
