# 전국 의미 태그 자동 수집

이 파이프라인은 서비스 사용자의 검증에 의존하지 않고 출시 전 의미 태그 근거를 매일 수집한다.
장소 분류나 업종은 의미 태그 수에 포함하지 않는다.

## 구성

- `PlaceTagCollectionJob`: 장소 하나의 당일 복수 의미 태그 수집 작업
- `ProviderQuotaUsage`: 공급자별 일일 예약·실제 호출량 원장
- `plan_daily_tag_collection`: 17개 시도와 장소 유형을 순환해 당일 작업 생성
- `process_place_tag_collection_jobs`: PostgreSQL 잠금으로 작업을 안전하게 선점하는 worker
- `recover_tag_collection_jobs`: 중단된 worker의 작업과 예약 쿼터 복구
- `run_tag_collection_scheduler`: 매일 계획 생성과 복구를 반복하는 상시 scheduler

한 장소에서 태그별로 검색하지 않고 장소 유형별 의미 묶음을 검색한다. 한 문서에서 여러 태그의
긍정·부정 근거를 추출하며, URL이 없는 결과나 장소 동일성이 부족한 결과는 저장하지 않는다.

## 안전장치

- 기본 일일 한도 25,000회 중 90%만 자동 작업에 사용
- 장소·공급자·날짜별 작업 중복 방지
- `SELECT FOR UPDATE SKIP LOCKED` 기반 다중 worker 안전 선점
- 30분 이상 멈춘 작업 자동 회수
- 실패는 최대 3회 지수 재시도
- 근거 없음은 실패가 아니라 완료로 기록
- 웹 근거는 candidate만 만들고 자동 confirmed 금지

## 실행

마이그레이션 후 Docker 프로필을 명시적으로 활성화한다.

```powershell
cd backend
.\venv\Scripts\python.exe manage.py migrate
cd ..
docker compose --profile tag-collection up -d --build tag_scheduler tag_worker
```

상태 확인:

```powershell
docker compose --profile tag-collection ps
docker compose logs --tail 100 tag_scheduler tag_worker
```

중지:

```powershell
docker compose --profile tag-collection stop tag_scheduler tag_worker
```

로컬 PC와 Docker Desktop이 꺼지면 수집도 멈춘다. 실제 운영에서는 같은 두 컨테이너를 항상 켜진
서버에서 실행해야 하며, `restart: unless-stopped`가 프로세스 장애와 서버 재부팅 후 재시작을 담당한다.

## 초기 운영값

처음에는 `TAG_COLLECTION_DAILY_PLACE_LIMIT=100`으로 24시간 검증한다. 장소 매칭률, 장소당 의미
태그 수, 근거 없음 비율과 태그별 precision을 확인한 뒤 500, 2,000, 7,500 순서로 올린다. 검색
호출량은 `ProviderQuotaUsage`에서 확인한다.
