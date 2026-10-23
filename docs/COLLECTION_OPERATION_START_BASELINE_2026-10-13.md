# 운영 P0 반영 여부·시작 기준선 — 읽기 전용 확인

**2026-10-13 13:37:36 KST 기준, 운영 P0 상세 계측은 미반영이다.** CPU 안전성 기반과 추가 schema는 유지돼 있지만 시간/품질/날짜 이벤트 구현은 없다. 따라서 P0 30분/자정 경계 관찰은 시작하지 않았다. 배포·설정 활성화·worker 추가 실행 없이 요청한 반영 여부와 시작 기준선만 확인했다.

## 조회 범위와 제한

- AWS 서울 리전의 기존 수집 인스턴스 `i-08cbd0f853d69ed38` 한 대와 worker/scheduler 두 컨테이너를 확인했다. SSM 실행 `c571d5eb-1217-4ec8-ae71-0c709d07001c`는 13:37:31~13:37:37 KST, Success/응답 0이었다.
- 컨테이너 metadata의 revision/running/restart/OOM, 코드 hash·허용 marker, 비밀값 없는 수집 설정만 읽었다. 전체 env/DB 접속 정보/원문 코드·장소·URL·인용문은 반출하지 않았다. Python은 -B로 실행했으며 임시 서버 파일을 작성하지 않았다.
- DB는 REPEATABLE READ, READ ONLY=on, transaction-local statement_timeout=2s/lock_timeout=200ms를 실제 확인했다. 작업·Evidence는 10월 12~13일/provider 또는 source로 제한했고 결과는 조회당 100행 이내였다. queue는 최대 501행, processing은 최대 100행의 제한된 하위 조회다.
- 주요 조회에 EXPLAIN FORMAT JSON(ANALYZE 없음)을 먼저 적용했다. 작업 날짜/provider 및 status 인덱스, Evidence created_at 인덱스, review evidence_id 인덱스를 확인한 뒤 집계했다. timeout/오류/중단 발생 없이 종료했다. DB 집계끼리는 같은 읽기 snapshot이며 CloudWatch/로그/컨테이너 시점까지 하나의 원자 snapshot은 아니다.
- 로그는 각 컨테이너 최근 30분·최대 2,000줄/5MiB로 읽고 숫자 이벤트의 존재·component 수만 출력했다. worker 0byte, scheduler 6,913byte, P0 이벤트 0개였다. 원문 로그는 저장하지 않았다. worker 무출력만으로 수집 정지라고 판단하지 않는다.

## 반영 여부

| 항목 | 직접 확인 |
|---|---|
| worker/scheduler revision | 모두 `76e2de2f9b30ad096022197dd946138d2a52668f` |
| 컨테이너 상태 | 모두 running, restart_count 0, OOMKilled false, 시작 시각 10월 11일 04:25:58 KST |
| CPU 기반 schema | reservation_date/quota_settled_at/result_checkpoint 존재, migration 0032 적용 시각 10월 11일 04:06:38 KST |
| P0 파일 | collection_telemetry.py와 summarize_collection_metrics.py 없음 |
| worker/report/planner/scheduler | P0 event·checkpoint 원래 시간·immutable completed_date 관련 marker 없음 |
| 작업 telemetry | 최근 이틀 계획일 대상 모든 상태에서 stats.telemetry 0건 |
| 최근 이벤트 | collection_metrics 허용 이벤트 0개 |

schema 0032 존재는 CPU checkpoint/정산 기반의 증거이며 P0 반영 증거가 아니다. 파일 부재·코드 marker·작업 stats와 로그를 함께 대조해 미반영으로 판단했다. 전체 소스 AST 비교나 모든 컨테이너/DB의 코드 감사는 이번 범위가 아니다.

유효 설정: provider naver_search, bounded/pacing 모두 true, 큐 LOW/HIGH 250/500, refill 100, scan page 2,000, planner SQL 2,000ms/lock 200ms/wall 5초, worker batch 10, 일일 API 설정 25,000·quota 비율 90%. 이 설정들은 변경하지 않았다.

## 자원 시작 기준선

CloudWatch CPU는 **13:00~13:30 KST의 완결 5분 구간 6개**다. 조회 시각은 약 13:34이며 서버 DB snapshot은 13:37이다. 실행 중인 최신 5분 구간은 포함하지 않았다.

| 구간 시작 KST | CPU Average | CPU Maximum |
|---|---:|---:|
| 13:00 | 5.83% | 6.04% |
| 13:05 | 6.10% | 6.37% |
| 13:10 | 5.87% | 6.39% |
| 13:15 | 5.72% | 6.23% |
| 13:20 | 6.41% | 7.04% |
| 13:25 | 5.75% | 6.47% |

평균은 구간별 5.72~6.41%, 표본 Maximum 최고는 7.04%였다. CPU·EC2 상태·scheduler-down·worker-down의 기존 경보 4개 모두 OK였다. 기존 CPU 경보는 5분/90%/2구간 설정이다. 관찰 계획의 50%/80% 제안과 구분하며 경보를 변경하지 않았다.

단일 docker stats 표본은 worker CPU 18.10%/메모리 36.75MiB, scheduler CPU 0.03%/79.35MiB였다. 컨테이너 단일 CPU 표본과 EC2 5분 평균은 지표 단위·시점이 달라 직접 비교하지 않는다. DB CPU·I/O·잠금 대기의 별도 계측은 하지 않았으므로 DB 전체 부하 안전을 단정하지 않는다.

## 작업·큐·quota 시작 기준선

다음은 **계획일 cycle_date별 누적 작업**이며 해당 날짜에 실제 완료된 작업 수가 아니다. 오늘은 13:37까지의 부분 일자다.

| 계획일 | completed | queued | Evidence 있는 completed | stats 신규 Evidence 합계 |
|---|---:|---:|---:|---:|
| 10월 12일 | 4,475 | 0 | 195 (4.36%) | 306 |
| 10월 13일 | 3,099 | 291 | 336 (10.84%) | 716 |

naver_search 전체 queued/retry는 291건(501행 한도 미도달)이었다. 최근 이틀 job checkpoint/미정산 checkpoint는 0건, provider 전체 processing 조회도 0건이었다. processing이 없어 이번 snapshot으로 실제 heartbeat 갱신·자정 재개·소유권 경쟁을 관찰하지 못했다. 오래된 계획일의 checkpoint는 이번 일자 집계 밖이다.

| 예약 usage_date | daily_limit 행 값 | 실제 정산 요청 | reserved | failed | rate_limited |
|---|---:|---:|---:|---:|---:|
| 10월 12일 | 25,000 | 8,261 | 0 | 0 | 0 |
| 10월 13일 | 25,000 | 7,137 | 0 | 0 | 0 |

설정과 행 값에 기반한 유효 예산 22,500 기준으로 오늘 남은 예약 가능량은 15,363회다. 이는 시점별 예약 여유이며 외부 API의 독립 quota 조회나 실제 요청 강제 상한 검증은 아니다. 실제 요청 수를 계획 요청 수로 절단하지 않는 CPU 정책을 유지한다. success_count도 위 요청 수와 같지만 품질 성공 의미는 아니다.

## Evidence 시작 기준선

네이버 Evidence의 **생성일 created_at** 집계이며, 유효 여부는 13:37 snapshot에서 판단했다. 미검토 review가 없는 근거는 기존 accepted 정책에 따라 포함할 수 있어 명시적 review 승인과도 분리했다.

| 생성일 | 신규 행 | 현재 유효 | 현재 유효·긍정·accepted | 현재 유효·긍정·명시적 review approved |
|---|---:|---:|---:|---:|
| 10월 12일 | 243 | 20 | 0 | 0 |
| 10월 13일(부분) | 779 | 86 | 0 | 0 |

job.stats 신규 Evidence 합계와 생성일 행 수는 날짜 귀속이 다르므로 동일해야 하는 값이 아니다. P0 미반영으로 단계별 시간·원래 checkpoint 수집 시간·immutable 완료일을 운영에서 측정하지 못했다. 신규 verified 태그는 이번 시작 조회에서 추가 집계하지 않았다. 이 표본으로 로컬 P0의 운영 품질 개선을 주장하지 않는다.

## 판정과 후속 경계

요청한 읽기 전용 시작 확인은 완료했다. 직접 확인한 자원 지표에서는 관찰 계획의 CPU/경보 중단 조건이 발생하지 않았고 SQL timeout도 없었다. 하지만 **P0 상세 계측 미반영이므로 상세 시간·날짜 경계 관찰을 진행할 조건은 충족하지 못했다.** 자연 수집이나 기존 서비스를 중지하지 않았다.

운영 설정/데이터/서비스/migration/배포 변경은 없다. AWS SSM 실행 기록과 통상적인 조회 로그만 생성될 수 있으며 업무 데이터에 쓰기 명령을 수행하지 않았다. 로컬에는 본 보고서와 CODEX_STATE의 milestone, 비밀값 없는 증거·보존 audit만 저장했다.

증거: `runtime/collection-start-baseline-20261013/evidence.json`. 관련 [관찰 계획](COLLECTION_LIMITED_OBSERVATION_PLAN_2026-10-13.md), [로컬 PostgreSQL 검증](COLLECTION_POSTGRES_VALIDATION_2026-10-13.md).

보존 audit: 기존 관련 파일 694개 중 690개 hash 동일, HEAD/index 동일. 작업 중 다른 채팅에서 T1_MASTER_CANDIDATE_REVIEW·SEARCH_PIPELINE_RELEASE_REVIEW·SEARCH_HYDRATION_REPEAT_REVIEW·GIT_INTEGRATION_PLAN 보고서 4개가 변경됐다. 이 채팅은 해당 파일을 쓰지 않았고 최신 변경을 보존했다. 공통 CODEX_STATE는 기존 내용을 유지하며 이번 milestone만 추가했다.

다음 한 가지 행동: P0 운영 반영을 원할 경우 검토된 선별 변경의 배포 후보와 되돌리기 절차를 별도 요청 범위로 준비한다. 이번 확인은 배포 승인이 아니다.
