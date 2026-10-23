# P0 수집 계측 — 로컬 구현과 검증

후속 완료: CPU 기반과 P0는 현재 checkout에 선별 통합됐다. 최신 결과와 checkpoint·정산 검증은 [통합 보고서](COLLECTION_TELEMETRY_INTEGRATION_2026-10-13.md)를 따른다. 아래 미통합 상태와 패치 설명은 이전 단계의 기록이며 동일 패치를 다시 적용하지 않는다.

## 변경 범위와 완료 상태

현재 codex/disk-maintenance checkout에서 수집 worker·계획기·scheduler·일일 보고에 계측을 추가했다. 기존 변경은 보존했고 운영 AWS 호출·설정·DB·마이그레이션·배포·commit/push는 실행하지 않았다. 테스트 DB는 config.test_settings의 메모리 SQLite다.

이 checkout에는 CPU 대응 기반의 bounded planner, pacing, reservation/checkpoint 모델이 없다. 다른 브랜치의 코드·migration을 공유 checkout에 섞지 않았다. 현재 경로는 직접 구현했고, 빠진 자원 제한 경로는 **76e2de2f9b30ad096022197dd946138d2a52668f 기준 통합 패치** `operations/collection-telemetry-resource-76e2.patch`로 작성했다. 단독 bounded 패치 `operations/collection-telemetry-bounded-76e2.patch`는 composite 패치에 포함된 동일 변경으로 둘을 중복 적용하지 않는다.

CPU 기반의 Python 소스만 `runtime/collection-telemetry-integration-76e2/`에 읽기 전용 Git 객체에서 복사하고 패치를 적용한 사본에서 검사했다. 현재 checkout/HEAD/index는 전환하지 않았다. 이 사본은 테스트용이며 운영 배포 꾸러미가 아니다.

## 지표 정의

- worker `stats.telemetry`: 처리 시작/종료 시각, cycle_date, 실제 completed_date, 예약일과 quota 정산 귀속일, attempt, monotonic 기반 claim/structured/collector/settle/save_and_finalize/processing 시간(ms), 추출 극성·강도·귀속 거절 수.
- `quality_at_save`: expired/reused/active_positive/active_accepted/active_positive_accepted를 별도 계수한다. accepted는 review 없음 또는 approved라는 기존 gate 정의다. positive와 현재 유효성·승인은 동의어가 아니다. 부정 승인도 active_accepted에는 포함되지만 active_positive_accepted에는 포함되지 않는다.
- `stats.attempt_metrics`: 최대 3회 처리의 작은 계측 payload를 유지한다. 원문/query/URL/사용자/장소 식별자는 계측 payload에 넣지 않는다. 기존 stats의 search_attempts 형식은 이번에 변경하지 않았다.
- processing_ms는 claim부터 마지막 job.stats 저장 **직전**까지다. collector/save/quota/structured 구간을 포함하지만 마지막 job.save 및 이벤트 출력 비용은 포함하지 않는다. 단조 시계로 계산하므로 자정·wall clock 보정에 영향을 받지 않는다.
- 현재 worker의 자정 경계에서는 이전 날 예약과 요청이 quota.usage_date에 정산되도록 reservation_date를 넘긴다. CPU 기반의 기존 예약일 귀속 정책을 따른다. 자정 후 다른 날짜의 예약을 차감하는 이전 로컬 코드 결함을 수정했다. 수집 강도·한도·채택 조건은 바꾸지 않았다. 오래된 로컬 경로의 중복 정산/checkpoint 안전성은 이 변경만으로 운영 기반과 같아지지 않는다.
- planner/scheduler/wait는 `collection_metrics` JSON 이벤트를 남긴다. 독립 logger의 INFO stream handler를 사용해 기존 전역 logging 설정을 변경하지 않고 출력한다. 같은 이벤트를 다른 부모 logger에 중복 전파하지 않는다. 별도 파일·DB schema·cloud resource를 만들지 않는다.
- `summarize_collection_metrics`는 stdin의 선택된 이벤트를 달력일/component별로 누적한다. 고정 whitelist의 숫자만 출력하고 그 외 줄·임의 key·원문은 제외한다. 이 도구는 DB/네트워크에 접근하지 않는다. 중복 없는 단일 로그 구간을 입력해야 하며, scheduler의 중복 planner payload는 합산 대상에서 제외한다. 일자 경계를 넘는 전체 duration은 이벤트 종료일에 배정한다는 메타데이터를 반환하므로 실제 자정 전후 초 단위 분할량으로 해석하지 않는다.

## 일일 보고

기존 키를 유지하면서 `periods`, `calendar_completion`, `naver.cycle_metrics`, 현재 유효·긍정·승인 수, 검토 상태 분포, 신규 verified PlaceTag 수를 추가했다.

jobs는 계획일, Evidence/새 PlaceTag는 생성일, quota는 **예약 usage_date**다. 현재 Evidence validity는 보고일 종료가 아니라 generated_at 시점이다. 과거 보고서를 재생하면 현재 검토/만료 상태로 계산하며, 과거 snapshot을 복원했다고 주장하지 않는다.

calendar_completion은 신규 immutable completed_date를 우선하고, 계측 이전 행은 updated_at proxy라는 별도 수로 표시한다. provider/cycle_date 인덱스 범위를 유지하기 위해 조회는 보고일 및 이전 7일 cycle로 제한한다. `cycle_window_start`와 `older_cycles_excluded=True`를 반환하므로 오래된 backlog를 포함한 전체 달력일 완료 수로 오해하지 않는다. 일간 보고는 stats 원문 전체 대신 필요한 JSON 하위 키만 읽는다.

cycle_metrics는 최신 attempt snapshot 합계와 보존 attempt 시간 합계를 각각 제공하고, 계측 없는 행을 unmeasured로 표시한다. 미계측 시간을 0으로 단정하지 않는다. 신규 verified 행과 기존 태그 상태 전환을 구분하며, 전환 이력이 없는 값은 null이다.

## 현재 계획기와 CPU 기반 패치의 차이

현재 legacy balanced/bootstrap은 기존 제한·선택 순서를 유지하며 후보 수, 선택 전후 budget 손실, shortfall, 계획 elapsed/tick 시간을 추가했다. SQL에서 이미 제외되어 읽히지 않는 recent/category/region 손실과 deadline은 `unmeasured_reasons`로 명시했다. 추가 전체 테이블 count/scan으로 손실 수를 추측하지 않는다.

CPU 기반 패치는 기존 2,000행 페이지·refill·시간/쿼터 제한·cursor rollback을 유지한다. 페이지 scanned/unique_candidates, consider 방문 수, recent/category_mismatch/category_cap/region_cap/region_mismatch, budget selection drop, 최종 cap, 요청 예산, cooldown/daily_cap/quota_budget/lock_busy/deadline_or_sql_timeout을 집계한다. 이는 방문/이벤트 수이며 고유 장소 수·기여 초와 다르다. category와 region 모두 막히면 먼저 실행된 분기만 센다. 동일 row가 demand/page에서 두 번 고려되면 방문은 두 번이다. 제한 때문에 검토하지 않은 페이지 나머지를 실패로 세지 않는다.

패치의 scheduler_queue 이벤트는 전체 queue depth와 backpressure/daily_cap을 기록하고, worker/scheduler wait는 요청 sleep·실측 sleep과 시작/종료일을 기록한다. worker pacing도 관측만 하고 기존 sleep 길이와 quota/checkpoint 정산을 유지한다.

## 검증

- 현재 checkout: collection telemetry, daily collection, daily report 관련 52개 테스트 통과 후 느린 collector monotonic 테스트를 추가하고 계측 테스트만 재검증했다. 자정 이월, insufficient의 completed/품질 분리, 기존 예약일 정산, pending/limited/부정/만료/재사용, retry attempt 보존, immutable 완료일, 누적 이벤트 whitelist를 확인했다.
- CPU 기반 사본: 기존 collection_resources 31개 중 24개 통과, 7개 skip. 새 bounded 계측 6개 모두 통과: recent/category/region 손실, quota/cooldown, deadline rollback, category cap, region cap.
- skip 7개는 PostgreSQL lock/SQL timeout 및 별도 heartbeat 실행 환경 검사다. SQLite 통과를 운영 PostgreSQL 동시성·최대 부하 검증으로 확대하지 않는다.
- composite 패치의 base 원본에 대한 apply check와 Python syntax 확인, 현재 변경의 diff whitespace 확인을 완료했다. 테스트 결과는 runtime/collection-telemetry-tests.txt, collection-telemetry-resource-tests.txt, collection-telemetry-bounded-tests.txt에 있다. 해당 파일은 합성 fixture 검사 기록이며 운영 원문 로그를 저장하지 않았다.

## 남은 일과 다음 한 가지 행동

로컬 경로 구현과 관련 검사는 완료했다. 공유 checkout에 CPU 기반을 통합하지 않았으며 운영에서는 새 계측이 아직 발생하지 않는다. 현재 로컬 worker 수정과 CPU 기반 worker를 파일 통째로 교체하면 checkpoint/정산 안전성을 잃을 수 있으므로 hunk 단위 통합이 필요하다. DB에 저장된 worker 계측과 logger 이벤트의 누적은 서로 다른 증거이며 로그 보존 기간 밖의 planner 이벤트는 복원할 수 없다.

**다음 한 가지 행동:** Git 통합 후보에서 CPU 기반을 보존한 채 P0 worker/report 변경과 composite 자원 계측 패치를 선별 통합하고 동일 관련 테스트를 실행한다.
