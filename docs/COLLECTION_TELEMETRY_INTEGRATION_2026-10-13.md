# CPU 기반과 P0 수집 계측 선별 통합

후속 완료: [격리 PostgreSQL 검증](COLLECTION_POSTGRES_VALIDATION_2026-10-13.md)에서 아래 환경 skip 7개를 실제 PostgreSQL 17.11로 모두 통과했다. 고유 관련 94개 검증 완료이며, 아래 skip/남은 PostgreSQL 문구는 이 후속 실행 이전 기록이다. 운영 검증과는 구분한다.

## 완료 상태

공유 codex/disk-maintenance checkout에 고정 CPU revision `76e2de2f9b30ad096022197dd946138d2a52668f`의 수집 기반과 P0 계측을 선별 통합했다. 운영 설정/서비스/데이터/배포·원격 병합·commit/push는 실행하지 않았다. HEAD와 Git index가 시작 시점과 같다.

이전 P0 보고서의 미통합·별도 CPU 사본 상태는 과거 단계다. 현재는 실제 checkout의 관련 파일에서 통합 검사를 실행했다. `operations/collection-telemetry-resource-76e2.patch`는 이미 반영한 역사적 패치이므로 다시 적용하지 않는다.

## 통합한 코드와 보존 기준

- worker: CPU 기반의 heartbeat, provider별 claim, 예약일, 정산 완료 표식, 실제 요청 수 정산, worker/attempt 소유권 검사, durable result checkpoint, materialization transaction, pacing을 보존했다. `claim_next_job`, `settle_quota`, `claim_heartbeat` 함수는 CPU 원본과 AST가 동일하다. 외부 결과 checkpoint 저장 → Evidence 저장 → 완료 시 checkpoint 제거의 순서를 유지했다.
- recovery: CPU 원본 파일과 같은 복구 로직을 가져왔다. 처리량 상한·예약일 기준 복구·이미 정산한 예약의 재차 차감 방지·checkpoint 보존이 포함된다.
- planner/scheduler: bounded 라우팅, 페이지/시간/SQL 제한, 큐 backpressure, cooldown, cursor/backoff, 적응형 선택의 CPU 개선을 보존하면서 P0 후보 손실/시간/대기 이벤트를 결합했다. outer planner와 bounded inner planner의 중복 계측 이벤트를 제거했다.
- models/settings: 추가 field 3개와 CollectionPlannerState, CPU의 자원 제한 설정 10개만 추가했다. settings에서 이 설정들을 제외한 AST는 시작 시점과 동일하므로 기존 검색/UI 담당 설정은 보존됐다. bounded/pacing 기본값은 CPU와 같은 false이며 이번에 활성화 환경 값을 바꾸지 않았다.
- migration: CPU 원본 `0032_collectionplannerstate_and_more.py`를 같은 이름·내용·0031 의존성으로 복원했다. 기존 migration 파일은 변경하지 않았다. 운영/기존 로컬 DB에 migrate하지 않았고 config.test_settings 메모리 SQLite에만 테스트 schema를 적용했다. 이는 새 정책 schema를 설계한 것이 아니라 누락된 CPU 기반 migration을 되가져온 것이다.
- 일보/누적 도구: P0의 생성/유효/긍정/승인/신규 verified·계획일/완료일/예약일 지표를 유지하고 checkpoint 재개 수·기존 checkpoint의 원래 수집 시간 미계측 수를 추가했다.

## checkpoint 계측 규칙

최초 외부 수집 결과에는 `_collection_telemetry`라는 작은 내부 메타데이터를 넣어 checkpoint와 함께 저장한다. 항목은 attempt, started_at, structured_ms, collector_ms뿐이며 원문/식별자/비밀값을 추가하지 않는다. Evidence 저장 도중 실패해도 이미 정산한 quota와 결과·원래 수집 시간이 남는다.

재개 시 현재 attempt의 collector_ms는 0이며 원래 수집 시간은 `telemetry.checkpoint_collection`로 분리한다. 예약일·정산 귀속일은 새 claim의 quota 행이 아니라 원래 job.reservation_date를 사용한다. 신규 형식이 없는 기존 checkpoint는 `checkpoint_collection_unmeasured=True`로 표시하고 원래 수집 시간을 만들어내지 않는다. 최대 3개 attempt 계측 기록은 최종 저장 transaction 안에서 갱신한다.

`worker_checkpoint.requests` 이벤트는 `settle_quota`가 이번에 정산한 경우만 실제 요청 수를 기록한다. 재개에서 이미 정산돼 있으면 0이다. `worker_attempt.requests`는 checkpoint에 있는 작업 결과의 요청 수이므로 재개에서도 원래 수가 들어갈 수 있다. component별로 별도 집계하며 두 이벤트의 요청 수를 더해 API 실호출 수라고 해석하지 않는다. 로그 유실 구간이나 collector 성공 직후 checkpoint 이전 프로세스 손실의 호출을 이 변경만으로 복원할 수는 없다.

## 검증 결과

- 최초 통합 회귀: `test_collection_telemetry`, `test_bounded_collection_telemetry`, `test_collection_resources`, `test_daily_tag_collection`, `test_report_daily_collection` 합계 90개에서 83개 통과·7개 skip.
- 추가 4개 통합 사례를 포함한 계측/ bounded 20개 모두 통과. 같은 날 기존 사례 반복을 중복 합산하지 않으면 **고유 관련 사례 94개, 통과 87개·skip 7개**다.
- 추가 사례: Evidence materialization 실패 후 자정 이월 복구/외부 호출 0/실제 요청 3의 단 한 번 정산, 기존 checkpoint 미계측 표시, 소유권을 잃은 collector 결과의 checkpoint·완료 계측 쓰기 차단, bounded router의 planner 이벤트 1회.
- 일보 checkpoint 수 추가 후 관련 3개를 재검증했다. 추천 모델 `makemigrations --check --dry-run --settings=config.test_settings`는 No changes detected로 통과했다. 운영 migration 실행 증거가 아니다.
- 기존 resource 검사는 actual request 초과 정산, 정산 두 번 방지, 이전 claim의 새 attempt 침범 방지, 정산한 예약 복구 시 재차 차감 방지, provider 분리, checkpoint 무호출 재개, 페이지·refill·쿼터 상한, cursor rollback을 검증한다.
- skip 7개는 원래 PostgreSQL·heartbeat 환경 전용 검사다. PostgreSQL locking/SQL timeout/실제 heartbeat thread에 대한 최종 검증과 운영 부하 검증은 남아 있다.
- whitespace 검사 통과. scoped 원본은 `runtime/collection-telemetry-merge-20261013/before/`, 안전성/보존 audit는 `audit.json`, 실행 결과는 `tests.txt`, `integration-tests.txt`, `report-final-tests.txt`, `schema-check.txt`에 있다. `integration-from-p0-checkout.patch`는 이번 시작 시점 P0 checkout 대비 기반 통합 delta이며, 이전 P0 신규 파일 자체는 포함하지 않으므로 단독 배포 꾸러미로 쓰지 않는다.

## 다른 작업 보존과 남은 일

수집 통합과 이번 보고서 갱신 대상 이외 149개 파일 fingerprint를 대조했다. 그중 147개는 동일하고, `docs/GIT_INTEGRATION_PLAN_2026-10-13.md`, `docs/SEARCH_PIPELINE_RELEASE_REVIEW_2026-10-13.md`는 작업 중 다른 채팅에서 변경됐다. 이 파일은 이번 채팅에서 쓰지 않았으며 최신 내용을 그대로 보존했다. 공통 CODEX_STATE.md에는 이번 milestone만 추가한다.

선별 통합과 로컬 관련 검사는 완료했다. 작업은 미커밋 상태이며 다른 공유 변경과 함께 있어 일괄 commit/push/배포하지 않았다. 운영 계측 실측, PostgreSQL/heartbeat 검증과 승인된 배포는 이번 완료 범위 밖이다.

**다음 한 가지 행동:** 격리된 로컬 PostgreSQL 환경에서 남은 SQL 제한·정산 경쟁·heartbeat 검사를 실행해 skip 항목을 검증한다.
