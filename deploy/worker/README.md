# EC2 태그 수집 worker 운영

이 Compose는 `deploy/db/docker-compose.yml`로 실행한 PostgreSQL 네트워크에
scheduler 1개와 worker 1개만 연결합니다. PostgreSQL 컨테이너를 새로 만들거나
기존 DB 데이터를 변경하지 않습니다.

## 사전 조건

- 저장소가 EC2에 체크아웃되어 있어야 합니다.
- `backend/.env`에는 외부 API 키가 있어야 하며 권한은 `600`이어야 합니다.
- `deploy/db/.env`와 `life-infra-map-runtime-db` DB 컨테이너가 이미 있어야 합니다.
- 집과 회사 컴퓨터의 로컬 scheduler/worker는 중지되어 있어야 합니다.

## 설정 검증

민감한 환경 변수 값을 출력하지 않는 검증 명령입니다.
DB 운영 디렉터리와 앱 소스를 분리한 EC2에서는 기존 DB 환경 파일의 절대 경로를
사용합니다.

```bash
docker compose \
  --env-file /home/ubuntu/life-infra-map/deploy/db/.env \
  -f docker-compose.yml \
  config --quiet
```

## 실행

`deploy/worker` 디렉터리에서 실행합니다.

```bash
docker compose \
  --env-file /home/ubuntu/life-infra-map/deploy/db/.env \
  -f docker-compose.yml \
  up -d --build --scale tag_worker=1
```

## 상태와 로그 확인

```bash
docker compose --env-file /home/ubuntu/life-infra-map/deploy/db/.env -f docker-compose.yml ps
docker compose --env-file /home/ubuntu/life-infra-map/deploy/db/.env -f docker-compose.yml logs --tail 100 tag_scheduler tag_worker
```

정상 상태에서는 다음 컨테이너만 각각 하나씩 보여야 합니다.

- `life-infra-map-tag-scheduler`
- `life-infra-map-tag-worker`

## 중지

DB 컨테이너에는 영향을 주지 않고 scheduler와 worker만 중지합니다.

```bash
docker compose --env-file /home/ubuntu/life-infra-map/deploy/db/.env -f docker-compose.yml stop tag_scheduler tag_worker
```
