# 제한 운영 계측 계획 — 대상·절차·중단 기준

작성일: 2026-10-13 KST. **문서 정리만 완료했으며 운영 조회·실행·배포는 하지 않았다.** 운영 설정과 데이터, 다른 채팅의 변경을 보존한다. 아래 수치와 관찰 횟수는 후속 실행을 위한 제안이며 기존 경보 설정이나 서비스 정책을 바꾸지 않는다.

## 실행 방식과 전제

기존 scheduler/worker가 자연스럽게 처리하는 작업을 읽기 전용으로 관찰한다. 추가 worker, 새 작업 계획, 수동 retry/recovery, 테스트 Evidence 생성, 검토/승인, 큐 수정, migration, 설정 변경, 서비스 재시작을 실행 절차에 넣지 않는다. 자연 수집에 따른 기존 서비스의 쓰기는 계속되지만 관찰자가 발생시키는 쓰기는 없다.

P0는 로컬 선별 통합과 관련 고유 94개 검사(그중 실제 PostgreSQL 7개)를 통과했다. 이는 운영 반영 증거가 아니다. 기록상 09:05의 운영 revision은 CPU 기반 `76e2de2f`였고 P0 배포를 확인한 적은 없다. 최신 운영 revision/schema/이벤트를 읽기 전용으로 확인하기 전까지 P0 상세 계측을 운영에서 얻을 수 있다고 가정하지 않는다.

P0가 없으면 기존 집계·CPU·서비스 상태의 기준선만 관찰하고 `상세 계측 미반영`으로 기록한다. 로그를 얻기 위해 즉석 배포하거나 설정을 활성화하지 않는다. P0 반영이 필요한 경우 별도 배포 검토와 실행 승인이 선행되어야 한다. 이번 계획은 배포 승인을 포함하지 않는다.

## 대상과 관찰 한도

| 대상 | 범위·확인할 내용 |
|---|---|
| 실행 환경 | 기존 수집 worker/scheduler와 같은 DB의 자원 상태. 읽기 전용 확인된 revision/schema, provider, bounded/pacing 유효 값, 재시작 수, 기존 경보 상태 |
| planner/scheduler | 자연 발생한 refill의 스캔·후보·작업 수, 탈락 사유, elapsed_ms, cooldown/backoff, queue_depth/backpressure. 설정상 페이지/refill/큐 제한과 비교 |
| worker | naver_search의 자연 실행 attempt. claim/structured/collector/settle/save_and_finalize/processing 시간, 상태, Evidence 생성·재사용·만료·유효 긍정 승인 수 |
| checkpoint/정산 | 원래 reservation_date와 quota usage_date, 정산 표식, 재개 시 외부 재호출·중복 정산 여부, 소유권 검사. 새 collector 실행을 유발하지 않음 |
| 날짜 경계 | cycle_date, completed_date, 예약일과 이벤트 기록일의 구분. 다음 날 실행/재개도 원래 예약일 정산 유지 |
| 자원 | 기존 CPU 5분 평균, DB/서비스 경보, heartbeat 갱신과 lease, 실제 요청·예약 잔액. 새 경보/대시보드 생성 없음 |

첫 관찰은 주간 **최대 30분 또는 worker_attempt 100개 중 먼저 도달할 때** 종료한다. 별도 날짜 경계 관찰은 안전 조건을 충족한 경우 **KST 23:50~다음 날 00:10, 최대 20분 또는 attempt 100개**로 제한한다. 이를 예약 작업으로 등록하지 않는다. 자정 이월·checkpoint 재개가 자연 발생하지 않으면 `미관찰`로 남긴다.

각 구간의 로그 입력은 최대 2,000개의 허용된 숫자 이벤트/5MiB, 시작·끝 로그 위치와 시간 범위를 고정한다. 한도를 넘으면 자료 수집을 끝내며 원문 로그로 범위를 확대하지 않는다. 이 한도는 수집 서비스의 작업/요청 수를 막는 기능이 아니라 관찰량 한도다. 자연 수집이 없어도 추가 작업을 넣지 않는다.

provider만으로 지역·카테고리의 표본 비율을 보장할 수 없다. 기존 작업 순서의 표본으로 명시하며 지역/카테고리를 맞추기 위해 우선순위·큐·설정을 바꾸지 않는다. 장소 이름·주소·URL·인용문·검색어·원문 diagnostics·인증 값은 반출하지 않는다.

## 실행 절차

1. **읽기 전용 확인을 별도 요청받은 뒤 시작한다.** 시작 KST/UTC, 대상 revision, worker/scheduler 수, 기존 경보, quota의 예약일·잔액을 기록한다. 서비스 설정은 비밀값 없는 허용 항목만 읽는다. P0 schema/코드 일치와 이벤트 유무가 확인되지 않으면 상세 계측 단계로 넘어가지 않는다.
2. **시작 기준선을 확보한다.** 직전 30분 자원/기존 서비스 지표와 현재 큐·processing/checkpoint 수, 최근 하루의 계획/완료/Evidence 집계를 같은 정의로 기록한다. 과거 보고서의 09:05/09:15 수치는 날짜가 명시된 참고값이며 현재 기준선으로 대체하지 않는다.
3. **DB 확인은 작은 읽기만 수행한다.** READ ONLY transaction에 SET LOCAL statement_timeout 2초, lock_timeout 200ms를 적용하고 즉시 종료한다. 읽기 transaction을 30분 유지하지 않는다. provider·일자·표본 작업 ID로 범위를 고정하고 각 조회 최대 100행, 시작/끝 한 번씩만 읽는다. 집계는 승인된 일자 구간만 사용하고 실행 계획을 먼저 확인한다. timeout이면 즉시 종료하며 timeout을 늘리거나 무제한 재시도하지 않는다.
4. **기존 로그/지표를 유한 구간에서 읽는다.** P0의 planner, scheduler_queue, worker, worker_checkpoint, worker_attempt 숫자 이벤트만 선별한다. 소스별 시작·끝 위치로 입력 중복을 막고 관찰 경계에서 진행 중인 attempt/checkpoint는 별도 표시한다. CPU/경보는 기존 5분 구간별 값으로 최대 6개(주간) 또는 4개(날짜 경계)를 확인한다. 상시 tail·반복 polling을 만들지 않는다.
5. **운영 상태를 건드리지 않고 로컬 집계한다.** 단계별 count/중앙값/p95/최댓값과 결측 수, 품질 분자/분모, 탈락 사유를 계산한다. 표본이 20개 미만이면 p95는 참고값으로 표시한다. 기존 summarize_collection_metrics는 합계만 제공하므로 그 출력으로 p95를 만들어내지 않는다. 숫자 이벤트와 집계 결과만 로컬에 저장한다.
6. **끝 기준선을 한 번 대조한다.** 마지막 시각, 자원/경보, 큐와 quota를 기록한다. 다른 worker가 진행 중이면 전체 quota 차이를 관찰 표본의 요청 합계와 같다고 단정하지 않는다. 단일 시점으로 잡을 수 없는 변화는 미확인으로 남긴다. 관찰 경계에서 진행 중인 작업은 서비스를 기다리거나 멈추지 않고 `진행 중`으로 분리한다.
7. **결과를 세 가지로 구분한다.** 안전 조건 충족 여부, 실제 관찰된 기능/결측, 품질 수율을 각각 기록한다. 읽기 경로 실패·자료 부족·미관찰은 성공 처리하지 않는다. 한 구간이 무사히 끝나도 자동으로 관찰 시간/표본/작업량을 확대하지 않는다.

### 현재 명령을 그대로 운영에 실행하지 않는 이유

- `process_place_tag_collection_jobs --limit N`은 작업을 claim하고 Evidence/quota를 쓰는 명령이다. 장소 ID 제한 옵션이 없고 `--watch` 없이 실행하면 pacing이 적용되지 않는다. `--watch --limit N`의 N은 전체 실행 상한이 아니라 반복 batch 크기다. 제한 관찰을 위해 새 worker를 실행하지 않는다.
- `run_tag_collection_scheduler --once`도 계획·복구·dashboard snapshot을 쓸 수 있다. 읽기 전용 관찰 명령으로 사용하지 않는다.
- `report_daily_collection --date`는 읽기 명령이지만 일자 전체 작업을 list로 적재하고 완료 집계는 7일 lookback을 포함한다. 이 명령 자체에 SQL/행 제한은 없다. 운영에서 곧바로 실행하지 않고 위 transaction 제한·실행 계획 확인을 갖춘 별도 읽기 절차를 사용한다.

## 중단 기준

여기서 **중단은 관찰자의 추가 로그/DB 조회와 후속 관찰을 끝내는 것**이다. 기존 worker/scheduler 중지·재시작·강제 kill·quota 수정·checkpoint 제거·복구 실행은 이 계획으로 승인되지 않는다. 실제 서비스 위험은 기존 운영 담당자의 장애 대응 절차로 넘긴다.

| 구분 | 관찰 종료/확대 금지 기준 | 후속 조치 |
|---|---|---|
| 자원/서비스 | 기존 CPU/DB/worker/scheduler 경보가 ALARM, 새 재시작·OOM·DB 오류 발생, 또는 CPU 5분 평균 80% 이상 1개 구간 | 즉시 추가 조회 종료, 기존 지표의 시각·오류 종류만 기록하고 담당자 판단으로 넘김 |
| 자원 조기 경계 | CPU 5분 평균 50% 이상 2개 연속 구간 | 현 구간 종료·다음 구간 보류. 절대 임계값은 임시 보수적 제안이며 기존 경보는 변경하지 않음 |
| SQL/관찰 부하 | 관찰 SQL의 2초 timeout/200ms lock timeout 발생, 실행 계획의 비제한 전체 스캔, 결과/로그 한도 초과 | 해당 읽기를 취소/rollback하고 재시도·범위 확장 금지 |
| 정산/소유권 | 실제 요청이 잘림, 중복 정산, 예약일 변경, 오래된 worker의 새 attempt 침범, 정산된 checkpoint의 외부 재호출 중 하나라도 직접 확인 | 안전성 실패로 기록, 관찰·확대 종료. quota/job/checkpoint를 수동 보정하지 않음 |
| heartbeat | 처리 중 locked_at이 30초 heartbeat 주기의 2배 이상 갱신되지 않음, 소유권 상실, checkpoint 저장 후 동일 작업의 중복 실행 의심 | 이상/미확인 구분 후 종료. 시간대·현재 lease를 확인할 수 없으면 정상이라고 판단하지 않음 |
| planner/collector | 현재 설정의 페이지/refill/큐/SQL 제한 위반, 같은 planner의 연속 timeout/backoff 2회, provider rate-limit/일일 예산 소진 | 후속 관찰 확대 중단. 예산/대기/설정을 완화하거나 작업을 강제로 재시도하지 않음 |
| 자료 무결성 | P0 event/schema 불일치, 날짜/기간 경계 불명확, 동일 로그 범위 중복, 비밀값·개인정보 포함 | 반출을 멈추고 해당 자료를 집계에서 제외. 원문 복사로 보완하지 않음 |
| 정상 종료 | 시간·attempt·입력량 한도 도달 | 예정대로 종료하고 관찰된 범위만 보고 |

heartbeat는 30초 갱신 구현을 기준으로 한 제안이다. 실제 lease/recovery 설정과 종료 직전 작업 상태를 시작 확인에서 대조해야 한다. heartbeat 오류는 기존 구현에서 thread가 종료될 수 있으므로 갱신 지연이 곧 데이터 손상임을 뜻하지는 않지만 정상으로 간주하지 않는다.

## 해석 기준과 결과 양식

- **계획/품질 분리:** completed나 quota success_count는 유용한 Evidence 확보를 보장하지 않는다. useful/completed, 신규 Evidence, 유효 긍정 승인 Evidence, 신규 verified 태그를 각 분모·관찰 시각과 함께 기록한다. 작은 표본에서 Evidence 0건만으로 서비스를 중단하거나 수율 개선을 주장하지 않는다.
- **요청/정산 분리:** 실제 요청 정산은 worker_checkpoint의 settled_now와 requests를 우선 확인한다. worker_attempt.requests는 checkpoint 재개 때 원래 요청 수를 반복할 수 있어 두 component를 더하지 않는다. 이벤트 유실·관찰 경계의 진행 중 작업은 DB 표식과 제한된 대조 없이는 실호출 수로 확정하지 않는다.
- **날짜 분리:** 작업은 cycle_date, 완료는 immutable completed_date, quota는 원래 reservation_date/usage_date, Evidence/신규 태그는 created_at 기준이다. 유효 여부는 조회 시각 기준이다. 구형 completed_date는 updated_at proxy임을 표시하며 7일 lookback 밖은 제외한다.
- **시간/재개 분리:** monotonic 단계 시간과 sleep을 분리한다. resumed checkpoint의 현재 collector_ms 0은 정상일 수 있다. 원래 시간은 checkpoint_collection로 별도 기록하며 구형 checkpoint 미계측 값을 0으로 대체하지 않는다. 이벤트 날짜별 합계는 전체 시간을 종료일에 귀속하므로 자정 전후 실제 시간으로 분할된 값이 아니다.
- **중복/표본 한계:** 현재 reducer는 입력 중복 제거·worker ID별 필터·분위수 계산을 지원하지 않는다. 이벤트만으로 특정 job을 확정할 수 없는 사례와 전 구간 대표성은 별도 한계로 기록한다.

보고 항목: 시작/끝 KST 및 UTC · revision/schema 확인 · 관찰 방식/한도 · 실제 attempt/이벤트 수 · 시작/끝 CPU·경보·큐·quota · 단계 시간과 결측 · 품질 분자/분모 · 정산/날짜/heartbeat 확인 및 미관찰 · 중단 기준 발생 여부 · 개인정보 없는 증거 위치 · 다음 행동 한 가지.

## 근거와 완료 범위

[CPU·P0 통합](COLLECTION_TELEMETRY_INTEGRATION_2026-10-13.md), [실제 PostgreSQL 7개 검사](COLLECTION_POSTGRES_VALIDATION_2026-10-13.md), [09:15 품질 분석](COLLECTION_QUALITY_FOLLOWUP_2026-10-13.md)과 현재 worker/scheduler/report/reducer 코드를 대조했다. 운영 상태를 이번에 재조회하지 않았다. 안전성 검증, 배포 상태, 운영 품질 개선은 서로 다른 증거다.

대상·실행 절차·중단 기준 정리는 완료했다. 다음 한 가지 행동: 읽기 전용 운영 확인을 요청받으면 P0 반영 여부와 시작 기준선을 유한 조회로 확인한다.
