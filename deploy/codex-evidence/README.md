# Codex 웹 근거 수집기

네이버 블로그 수집과 별도로, 서버의 Codex CLI를 ChatGPT 계정으로 실행해 부족한 태그의
공개 웹 근거를 찾는다. 초기 기본 배치는 카페 1곳과 음식점 1곳이며 매일 03:40 KST 이후 한 번 실행한다.
최근 14일 결과 파일에 포함된 장소는 제외해 같은 실패 대상을 반복 조사하지 않는다.

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
sudo install -m 0644 deploy/codex-evidence/life-infra-map-codex-evidence.service /etc/systemd/system/
sudo install -m 0644 deploy/codex-evidence/life-infra-map-codex-evidence.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now life-infra-map-codex-evidence.timer
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
