# P0 통합 후 격리 PostgreSQL 검증

2026-10-13 실제 공유 checkout의 남은 PostgreSQL 전용 검사 **7개 모두 통과, skip 0**, 실행 시간 6.309초. 앞선 SQLite 검사와 합치면 고유 관련 사례 94개를 모두 검증했다. 이번에는 애플리케이션 소스를 수정하지 않았다.

## 격리 범위

- 설치 프로그램이나 Docker Desktop을 기동하지 않고 [EDB 배포 바이너리](https://www.enterprisedb.com/download-postgresql-binaries?lang=en) PostgreSQL 17.11을 임시 폴더에 압축 해제했다.
- 전용 클러스터는 `runtime/collection-postgres-20261013/data-final`, 주소는 `127.0.0.1:63969`, 테스트 계정은 collection_test였다. 실제 서버 주소·포트·data_directory를 SQL로 검사해 이 임시 클러스터와 일치함을 확인했다.
- dotenv 로딩을 차단하고 테스트 DB 설정을 메모리에서 고정했다. 운영 접속 정보·운영 설정·기존 DB·서비스·배포는 사용하거나 변경하지 않았다. 초기 제한 실행에서 완료되지 않은 클러스터를 재사용하지 않았다.
- 일반 테스트 schema는 모델로 생성했다. PostGIS/검색 인덱스의 전체 과거 migration 검증은 이번 범위 밖이다. 추가 migration 0032 검사는 임시 DB에서 0031 모델 상태의 기존 작업을 만들고 실제 0032 DDL을 적용했다.

## 검사 결과

| 검사 | 확인 결과 |
|---|---|
| SQL 제한 복원 | 정상 종료·SQL 오류 후 statement_timeout 복원, planner 내부 병렬 worker 제한 0 |
| statement timeout | 30ms 제한으로 pg_sleep(100ms) 취소, rollback 후 SELECT 42 성공 |
| planner backoff | 두 번의 timeout에 cursor 0 유지·job 미생성·연속 실패 1/2와 누적 대기 기록 |
| 대형 합성 데이터 | 20,000행 중 스캔 2,000·후보 300·작업 100, EXPLAIN Limit 및 PK 인덱스 확인 |
| 추가 migration | 기존 queued job과 planned_requests 2 유지, 새 예약일/checkpoint nullable |
| 실제 heartbeat | 별도 DB 연결 thread가 오래된 claim의 locked_at 갱신 |
| 실제 claim 경쟁 | 다른 연결이 잠근 첫 행을 skip_locked로 건너뛰고 두 번째 작업 claim |

대형 데이터 planner 관측 시간은 304ms, 쿼리 437개였다. 이는 로컬 합성 사례의 수치이며 운영 부하 성능이나 모든 정산 경쟁 시나리오의 증거로 확대하지 않는다. CPU checkpoint/정산 안전성은 앞선 통합 회귀와 함께 판단한다.

## 종료·보존 확인

테스트 runner의 전용 test_collection_resource_test DB 생성/삭제와 성공 종료를 확인했다. pg_ctl fast stop 성공, PostgreSQL 로그의 `database system is shut down`, postmaster.pid 부재를 확인했다. 공유 소스·문서 범위 hash 변화 0, HEAD/index 변화 0이었다. 이 확인 후 본 보고서·통합 보고서·CODEX_STATE에 이번 milestone만 기록했다.

증거와 재현 runner는 `runtime/collection-postgres-20261013/`의 `tests-final.txt`, `postgres.log`, `audit.json`, `before.json`, `run_checks.py`에 있다. 임시 바이너리·다운로드·클러스터는 종료 확인 후 제거한다. 소스 변경·commit/push·운영 migration 실행은 없다.

요청한 로컬 PostgreSQL 검증은 완료했다. 후속 운영 계측은 별도 요청 범위다.
