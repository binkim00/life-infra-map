# 서버 디스크 자동 관리

루트 디스크를 6시간마다 확인하고, 사용률이 80% 이상 또는 여유 공간이 5 GiB 미만이면 기존 SNS 알림 주제로 주의 알림을 보냅니다. 90% 이상 또는 2 GiB 미만이면 긴급 알림을 보냅니다. 상태가 바뀔 때만 알리고, 90일간의 측정 기록을 `runtime/disk-maintenance/history.jsonl`에 유지합니다.

매주 월요일 UTC 04:15에 Docker의 **7일 넘은 빌드 캐시**만 정리합니다. 캐시 2 GB는 남기며 이미지, 실행 중인 컨테이너, 볼륨, DB, 배포 백업은 삭제하지 않습니다. 배포가 잠시 느려질 수는 있지만 이미지 롤백 자산은 유지됩니다.

## 설치

서버의 `/home/ubuntu/life-infra-map/app`에 이 디렉터리를 배치한 뒤 운영자가 다음을 실행합니다.

```bash
sudo install -m 0644 deploy/disk-maintenance/life-infra-map-disk-monitor.service /etc/systemd/system/
sudo install -m 0644 deploy/disk-maintenance/life-infra-map-disk-monitor.timer /etc/systemd/system/
sudo install -m 0644 deploy/disk-maintenance/life-infra-map-build-cache-cleanup.service /etc/systemd/system/
sudo install -m 0644 deploy/disk-maintenance/life-infra-map-build-cache-cleanup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now life-infra-map-disk-monitor.timer life-infra-map-build-cache-cleanup.timer
sudo systemctl start life-infra-map-disk-monitor.service
```

## 확인

```bash
systemctl list-timers --all 'life-infra-map-*disk*' 'life-infra-map-*cache*'
systemctl status life-infra-map-disk-monitor.service --no-pager
journalctl -u life-infra-map-disk-monitor.service -n 20 --no-pager
journalctl -u life-infra-map-build-cache-cleanup.service -n 20 --no-pager
tail -n 10 /home/ubuntu/life-infra-map/runtime/disk-maintenance/history.jsonl
df -h /
```

첫 실행에서 현재 80% 이상이면 주의 알림 한 건이 전송됩니다. SNS 구독이 확인되지 않은 수신자에게는 메일이 도착하지 않으므로 실제 도착도 확인해야 합니다. 디스크 사용량이 캐시 정리 후에도 계속 증가하면 EBS 증설을 별도로 결정합니다.
