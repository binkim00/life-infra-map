# 운영용 경량 DB 준비와 배치

## 목적

현재 개발 DB의 약 12GB는 `SourcePlaceRecord` 440만 건이 차지합니다. 이 데이터는
전국 파일을 다시 정규화하거나 변경점을 비교할 때 사용하는 작업 원본이며, 사용자
검색과 태그 worker는 정규화된 `Place`를 사용합니다.

운영용 DB에는 다음 데이터를 그대로 보존합니다.

- `Place`, `Tag`, `PlaceTag`, `PlaceTagEvidence`
- `PlaceTagCollectionJob`, quota와 수집 이력
- 사용자, 게시판, 저장 및 신고 데이터
- Django/Spring이 사용하는 전체 스키마와 PostGIS 확장

다음 두 테이블은 스키마만 유지하고 운영용 dump에서는 행을 제외합니다.

- `recommendations_sourceplacerecord`
- `recommendations_kakaoplacematch` — 원본 행만 참조하는 매칭 작업 결과

원래 개발 DB는 변경하거나 삭제하지 않습니다. 원본 CSV와 전체 DB dump는 별도
아카이브로 보관합니다.

## 1. 경량 복제 DB 생성

프로젝트 루트의 PowerShell에서 실행합니다.

```powershell
.\scripts\db\prepare-runtime-db.ps1
```

스크립트는 다음 안전 검사를 수행합니다.

1. 기존 `life_infra_map` DB는 읽기만 함
2. `life_infra_map_runtime`이라는 새 DB를 생성함
3. 원본 두 테이블의 데이터만 제외해 복제함
4. 장소·태그·근거·worker·사용자 테이블의 원본/복제 건수를 비교함
5. PostGIS 동작과 최종 DB 크기를 확인함
6. `backend/tmp/db/`에 서버 복원용 custom-format dump와 SHA256을 생성함

같은 이름의 대상 DB가 이미 있으면 덮어쓰지 않고 중단합니다. 다시 시험할 때는 새
이름을 지정합니다.

```powershell
.\scripts\db\prepare-runtime-db.ps1 -TargetDatabase life_infra_map_runtime_v2
```

이미 생성된 대상의 건수 검증과 dump 생성만 다시 실행하려면 `-VerifyOnly`를 사용합니다.

```powershell
.\scripts\db\prepare-runtime-db.ps1 -VerifyOnly
```

dump가 필요 없는 검증용 복제만 만들려면 `-SkipDump`를 사용합니다.

## 2. 서버 DB 실행

서버의 `deploy/db` 디렉터리에서 환경 파일을 만듭니다.

```bash
cp .env.example .env
```

`POSTGRES_PASSWORD`를 긴 임의 문자열로 교체합니다. PostgreSQL 5432 포트를 인터넷
전체에 공개하지 않습니다.

- API 서버와 DB가 같은 서버라면 `POSTGRES_BIND_IP=127.0.0.1`
- 집 노트북 worker가 연결해야 한다면 서버의 Tailscale IP(`100.x.y.z`)만 사용

컨테이너를 시작합니다.

```bash
docker compose --env-file .env up -d db
docker compose --env-file .env ps
```

## 3. 경량 dump 복원

생성된 `.dump` 파일을 서버의 `deploy/db/backups/`에 복사한 다음 실행합니다.

```bash
docker compose --env-file .env exec -T db \
  pg_restore --exit-on-error --clean --if-exists --no-owner --no-privileges \
  -U life_infra_map -d life_infra_map /backups/life_infra_map_runtime-YYYYMMDD-HHMMSS.dump
```

복원 후 확인합니다.

```bash
docker compose --env-file .env exec -T db \
  psql -U life_infra_map -d life_infra_map -c \
  "SELECT pg_size_pretty(pg_database_size(current_database()));"
```

## 4. 집 노트북 worker 연결

집 노트북의 `backend/.env`에서 접속 대상만 서버로 변경합니다.

```text
POSTGRES_HOST=서버의_Tailscale_IP
POSTGRES_PORT=5432
POSTGRES_DB=life_infra_map
POSTGRES_USER=life_infra_map
POSTGRES_PASSWORD=서버에서_설정한_비밀번호
```

태그 scheduler와 worker는 `SourcePlaceRecord`가 아니라 `Place`와
`PlaceTagCollectionJob`을 사용하므로 경량 DB에서도 같은 방식으로 동작합니다.

## 5. 원본 갱신 방식

원본 파일 갱신은 운영 DB와 분리합니다.

1. 새 원본 파일과 이전 원본 파일을 보관
2. 별도 임시 DB나 로컬 개발 DB에 `SourcePlaceRecord`로 적재
3. 신규·변경·폐업을 비교하고 `Place` 변경분 생성
4. 검증된 변경분만 운영 DB에 반영
5. 임시 DB 제거

일반 음식점·카페 검색은 Kakao Local API로 처리하고, 운영 DB는 공공 인프라와 자체
태그, 사용자가 실제로 사용한 Kakao 장소를 중심으로 유지합니다.
