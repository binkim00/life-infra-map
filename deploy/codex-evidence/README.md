# Codex 웹 근거 수집기

네이버 블로그 수집과 별도로, 서버의 Codex CLI를 ChatGPT 계정으로 실행해 부족한 태그의
공개 웹 근거를 찾는다. 부산 집중 단계의 운영 기본 배치는 카페 25곳과 음식점 25곳이며
매일 03:40 KST 이후 한 번 실행한다. 부산 품질·밀도 목표를 확인한 뒤 서울, 광역시, 전국 순으로
보강 범위를 넓힌다.
직전 1일 결과에 포함된 장소만 제외한다. 품질 테스트 상위에 반복 노출되지만 근거가 부족한 장소는
하루 뒤 다시 조사해 한 장소의 추천 근거를 여러 관점으로 깊게 만든다. 제외 기간은
`CODEX_EVIDENCE_REVISIT_DAYS`로 조정할 수 있다.

매일 품질 평가가 상위 5개 DB 장소의 `missing_conditions`와 `unverified_conditions`를
`TagEnrichmentRequest`에 적재한다. 다음 Codex 실행은 이 장소와 태그를 일반 Coverage 대상보다
먼저 고른다. Naver가 찾아 둔 URL은 Codex에 전달하기 전에 운영 서버와 같은 본문 수집기로
사전 검사하며, 읽을 수 없는 URL은 힌트에서 제외한다. 장소당 서로 다른 태그 근거를 최대 3개까지
찾아 저장할 수 있다.

Codex 결과는 곧바로 신뢰하지 않는다. Django 검증기가 서버에서 URL을 다시 가져오고 다음 조건을
모두 확인한 결과만 `PlaceTagEvidence(source=web_search)`로 저장한다.

- DB의 장소 ID, 이름, 카테고리 및 정식 태그 일치
- 허용된 공개 URL과 robots.txt 정책 통과
- 서버가 다시 받은 본문에 장소명과 인용문이 실제로 존재
- 규칙 기반 polarity 판정 일치
- 동일 URL, 태그, polarity 중복 방지

## 최초 설치

공식 설치 스크립트로 CLI를 설치하고 `codex login --device-auth`로 `ubuntu` 계정에 로그인한다.
그 다음 배포 파일을 설치한다.

```bash
sudo install -m 0755 deploy/codex-evidence/run-codex-evidence.sh /home/ubuntu/life-infra-map/app/deploy/codex-evidence/run-codex-evidence.sh
sudo install -m 0755 deploy/codex-evidence/start-catchup-if-stale.sh /home/ubuntu/life-infra-map/app/deploy/codex-evidence/start-catchup-if-stale.sh
sudo install -m 0755 deploy/codex-evidence/publish_failure_alert.py /home/ubuntu/life-infra-map/app/deploy/codex-evidence/publish_failure_alert.py
sudo install -m 0644 deploy/codex-evidence/life-infra-map-codex-evidence.service /etc/systemd/system/
sudo install -m 0644 deploy/codex-evidence/life-infra-map-codex-evidence.timer /etc/systemd/system/
sudo install -m 0644 deploy/codex-evidence/life-infra-map-codex-evidence-failure.service /etc/systemd/system/
sudo install -m 0644 deploy/codex-evidence/life-infra-map-codex-evidence-catchup.service /etc/systemd/system/
sudo install -m 0644 deploy/codex-evidence/life-infra-map-codex-evidence-catchup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now life-infra-map-codex-evidence.timer life-infra-map-codex-evidence-catchup.timer
```

## 소규모 수동 검증

```bash
CODEX_EVIDENCE_CAFE_LIMIT=1 CODEX_EVIDENCE_RESTAURANT_LIMIT=1 \
  ./deploy/codex-evidence/run-codex-evidence.sh
sudo systemctl status life-infra-map-codex-evidence.timer
sudo journalctl -u life-infra-map-codex-evidence.service -n 100 --no-pager
```

원본 후보와 결과 JSON은 `/home/ubuntu/life-infra-map/runtime/codex-evidence`에 14일 보관한다.
API 키는 사용하지 않으며, 실행량은 ChatGPT 플랜의 Codex 사용 한도에 포함된다.

수집 실패 시 서비스는 15분 간격으로 최대 3회 실행을 시도한다. 첫 실패 알림은 SNS
`life-infra-map-alerts`로 전송하고 6시간 동안 중복 알림을 억제한다. 네트워크 장애 때문에
즉시 보내지 못한 알림 서비스는 5분마다 다시 시도한다.

`life-infra-map-codex-evidence-catchup.timer`는 부팅 5분 뒤부터 30분마다 마지막 검증 성공
결과를 확인한다. 성공 결과가 14시간 이상 오래되었으면 수집 서비스를 한 번 시작하여
서버 중단 중 놓친 주기를 보충한다. 이 기준은 `CODEX_EVIDENCE_MAX_AGE_SECONDS`로 조정한다.

CloudWatch 경보 `life-infra-map-ec2-status-check-failed`는 `StatusCheckFailed > 0`이 2분
지속되면 SNS 알림과 함께 EC2 재부팅 작업을 실행하도록 유지한다. 정상 전환 알림도 같은
SNS 주제로 전송하여 자동 복구 완료 여부를 확인할 수 있게 한다.
