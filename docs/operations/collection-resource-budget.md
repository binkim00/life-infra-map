# 수집 작업의 DB 자원 제한과 복구

## 변경 기준과 범위

시작 커밋: `5550de6532ae014ec6cbf923ebc0659097e1a2c2`
(`origin/codex/release-foundation`). 수집 관련 파일은 fetch 시점의
`origin/master`와 같았다. 기존 `kyb` 체크아웃과 사용자 파일은 보존했다.
작업 브랜치는 `codex/collection-resource-budget`이며 운영 반영과 push는 하지 않았다.

운영에서 확인한 직접 부하는 tag scheduler 연결의 PostgreSQL SELECT와 두 병렬
작업자였다. DB 컨테이너 CPU가 약 195%였고, 전역 statement_timeout은 0이었다.
모든 과거 CPU 알람의 원인이 동일했다고 확정한 것은 아니다.

## 구현

- 큐가 250개 이상이면 재계획하지 않는다. 한 번에 최대 100개를 보충하며 큐 상한은 500개다.
  queued/retry를 모두 포함하므로 미래 재시도도 무한히 쌓이지 않는다.
- 새 계획기는 기본키 순서로 최대 2,000개의 `id/category/address/detail_location`만 읽는다.
  주소 접두사 검사는 이 페이지에서 수행한다. 전체 Place의 지역별 COUNT나
  주소 검색, 중첩된 demand Place 서브쿼리는 사용하지 않는다.
- 수요 ID를 먼저 제한해서 읽고 발견 후보와 함께 최대 300개만 점수화한다.
  기존 우선순위·증거 품질·목표 태그 계산을 재사용한다. 페이지에 없는 고우선순위
  후보의 발견이 늦어질 수 있으므로 기존의 전체 후보 순서와 같지는 않다.
- 커서, 다음 실행 시각, 비민감 수치 지표는 CollectionPlannerState에 보관한다.
  계획 작업과 커서 갱신은 함께 커밋한다. 예산·선택 상한으로 미처리 후보가 남으면
  커서를 보존한다. 재시작해도 이어가며 같은 공급자의 계획기는 행 잠금으로 직렬화한다.
- PostgreSQL 제한은 해당 트랜잭션에만 적용한다: statement_timeout 2초,
  lock_timeout 200ms, 병렬 gather 작업자 0. 연결이나 DB의 전역 설정은 바꾸지 않는다.
  트랜잭션 작업 예산 5초를 SQL 경계에서 검사한다. 진행 중인 SQL은 최대 2초의
  statement timeout으로 끝나므로 이는 정확한 5초짜리 강제 CPU 제한은 아니다.
- 시간 초과는 커서와 생성 작업을 롤백하고 60→120→240→480→900초 백오프로
  물러난다. 성공 시 백오프가 초기화된다. 호스트 CPU 백분율 제어나 자동 스케일링은 없다.
- 일일 작업 생성 목표, 명시적인 지역별 비중, 카테고리 상한, 재방문 기간과 API
  안전 예산을 유지한다. 6,000은 생성 작업 목표이며 유용한 증거 6,000개를 보장하지 않는다.
  기존 품질/탐색 버킷의 API 예산 배분과 hard cap도 재사용한다. 최근 최대 5,000개씩의
  학습 이력은 전체 JSON 대신 필요한 수치 필드만 읽고 같은 DB 시간 제한을 적용한다.
- 작업자의 watch 모드에는 작업당 목표 간격을 두는 선택 스위치를 추가했다.
  6,000개/일이면 약 14.4초다. 실제 처리 시간을 빼고 쉬며 빠른 반복으로 따라잡지 않는다.
- 예약 날짜를 저장해 자정 이후에도 원래 날짜에 정산한다. 정산 마커로 중복 정산을
  막고, 실제 API 호출 수를 예약 예상치로 잘라 숨기지 않는다.
- 외부 호출 결과와 정산을 먼저 저장한다. 이후 증거 저장에 실패하면 그 결과를
  재사용한다. 복구 시 이미 정산된 예약을 다시 해제하지 않는다.
- 상태·worker ID·시도 횟수를 확인해 회수된 작업의 이전 작업자가 결과를 쓰지 못하게 한다.
  실제 수집 중에는 별도 연결에서 30초마다 잠금을 갱신한다.
- 추가 마이그레이션 0032는 nullable 정산/결과 필드와 작은 계획 상태 테이블만 추가한다.
  기존 증거·큐를 삭제하거나 Place의 대형 인덱스를 생성하지 않는다.

## 테스트 환경과 재현

Windows KYB, 프로젝트 전용 `.venv`, Python 3.14.3, 저장소 requirements.txt의
정확한 버전(Django 6.0.5, psycopg 3.2.10)을 사용했다. 시스템 패키지 접근은 끈 상태다.
PostgreSQL 16.15 공식 EDB 바이너리는 작업 폴더의 독립 런타임으로 실행했다.
운영 데이터, 운영 자격증명, 기존 `.env`는 복사하지 않았다.

TCP 연결은 실행 환경에서 거절/시간 초과되어 방화벽 변경 없이 Windows 파일 소켓으로
연결했다. PostgreSQL 테스트 설정은 전용 포트 55439와 테스트 DB만 사용한다.
권장 재현 명령의 소켓 경로는 자신의 작업 폴더 경로로 바꾼다.

```powershell
$env:COLLECTION_TEST_SOCKET_DIR='C:/Users/k0b03/Documents/Codex/2026-10-11/task/pgsocket'
.venv/Scripts/python.exe backend/manage.py test recommendations.test_collection_resources recommendations.test_daily_tag_collection recommendations.test_adaptive_budget recommendations.test_bootstrap_reporting recommendations.test_report_daily_collection recommendations.test_place_evidence_completeness --settings=config.collection_pg_test_settings --noinput
.venv/Scripts/python.exe backend/manage.py test recommendations.test_collection_resources recommendations.test_daily_tag_collection recommendations.test_adaptive_budget recommendations.test_bootstrap_reporting recommendations.test_report_daily_collection recommendations.test_place_evidence_completeness --settings=config.test_settings --noinput
.venv/Scripts/python.exe backend/manage.py makemigrations --check --dry-run --settings=config.test_settings
.venv/Scripts/python.exe -m pip check
git diff --check
```

PostgreSQL 회귀 환경은 현재 모델로 테스트 스키마를 만든다. 전체 과거 PostGIS/검색
인덱스 마이그레이션은 실행하지 않는다. 별도 테스트에서 0031 모델 상태의 기존 작업을
만들고 실제 0032 마이그레이션을 적용해 큐 보존을 확인한다.
잠금, heartbeat, SQL 시간 초과/복원, 계획기 시간 초과 백오프는 실제 PostgreSQL에서 검증한다.

합성 성능 테스트는 장소 20,000개(각 raw에 2KB)를 만들고 ANALYZE 후 실행한다.
페이지 2,000개, 점수 후보 300개, 작업 100개 및 기본키 인덱스 EXPLAIN을 확인한다.
최종 bootstrap 모드 PostgreSQL 실행은 81/81개 통과, 13.432초였다. 합성 계획은
332ms/435개 SQL이었다. SQLite 실행은 74개 통과, PostgreSQL 전용 7개 제외,
6.455초였다. 모델/마이그레이션 차이 검사, pip check, git diff --check도 통과했다.
격리 DB는 locale C, max_connections 20, shared_buffers 400kB로 초기화됐으며 운영과 다르다.
운영 125만 건의 부하나
호스트 CPU 감소율을 재현한 벤치마크는 아니다.

## 적용과 복구 조건 — 실행하지 않음

운영 적용은 별도 승인 후 진행한다. 먼저 실행 중인 기존 worker를 안전하게 마치고,
추가 마이그레이션 0032를 적용한 다음 같은 버전의 scheduler/worker를 시작해야 한다.
새 코드의 worker는 스위치가 꺼져 있어도 새 필드가 필요하므로 마이그레이션을 생략할 수 없다.
기존/새 worker를 동시에 돌리지 않는다.

`TAG_COLLECTION_BOUNDED_PLANNER_ENABLED=true`와
`TAG_COLLECTION_WORKER_PACING_ENABLED=true`는 검증 후 명시적으로 켠다. 기본값은 false다.
초기 값은 큐 low/high 250/500, refill 100, page 2,000, statement/lock 2,000/200ms,
wall 5초, cooldown 60초다. scheduler 로그와 계획 상태의 scanned/candidates/elapsed_ms/deferred,
DB CPU, API 호출 수, 유용한 증거 비율과 지역·카테고리 분포를 함께 관찰한다.
처음에는 작은 범위로 후보 순서와 품질 변화가 허용되는지 확인한다.

문제가 있으면 새 worker의 정산/체크포인트 처리는 유지하고 계획기 스위치만 끌 수 있다.
전체 코드 롤백은 저장된 미완료 결과가 없는지, 진행 중 작업과 정산이 정리됐는지 확인한 뒤 한다.
추가 컬럼/상태 테이블은 보존하며 마이그레이션을 역적용하거나 큐·증거를 삭제하지 않는다.

외부 API가 끝난 직후 결과 체크포인트를 쓰기 전에 프로세스가 사라지는 구간은
호출 사실을 완전히 복원할 수 없다. 수집 API의 idempotency/요청별 영수증이 없으므로
그 구간까지 exactly-once 호출이나 정확한 사용량을 보장하지 않는다. 이미 저장된 결과의
증거 재처리와 정산에는 중복 방지가 적용된다. 단일 서버에서의 장기 처리량·운영 CPU와
이 불확실 구간에 대한 운영 정책은 운영 적용 전 확인할 사항이다.

공식 테스트 런타임 출처:
[EDB PostgreSQL 바이너리](https://www.enterprisedb.com/download-postgresql-binaries),
[PostgreSQL 연결/파일 소켓 설정](https://www.postgresql.org/docs/16/runtime-config-connection.html).
