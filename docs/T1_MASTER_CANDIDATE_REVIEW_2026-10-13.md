# T1 수집 P0 계측 — master 기반 격리 후보 검증

## 결과

요청한 master `84e3ebf780d4cb53041c8721b929c5a52bd0fccd` 위에 T1 잔여 9파일만 반영한 격리 후보를 구성했다. 후보 Git tree는 `c70e09152b93db3d5bfa2d60c6577cc70c3ed9b0`이며 실제 commit/branch 생성·push·PR·운영 배포는 하지 않았다.

관련 5모듈 **94개 검사 중 87개 통과, PostgreSQL 전용 7개 제외**, 실패·오류 0이다. 검사 실행 3.143초, runner 및 schema 검사 포함 9.562초다. system check 정상, `makemigrations recommendations --check --dry-run`은 No changes detected다. 현재 후보 구성·검사에서 재현된 차단 문제는 없다.

## 후보 구성과 경계

공용 index 대신 runtime 별도 index/objects에 master tree를 읽고 재분류 때 동결한 T1 blob만 적용했다. 적용 전 현재 공유 9파일 SHA256이 재분류 snapshot과 같음을 확인했다. master→후보 변경 경로는 정확히 아래 9개다. 다른 파일은 master 내용을 유지한다.

| 경로 (backend/recommendations/ 기준) | 추가/삭제 행 | 내용 |
|---|---:|---|
| management/commands/plan_daily_tag_collection.py | 17 / 2 | legacy·bounded planner 시간과 후보 부족/예산 지표 |
| management/commands/process_place_tag_collection_jobs.py | 64 / 4 | 단계 시간·근거 품질·checkpoint 재개·예약/완료 날짜·대기 계측 |
| management/commands/report_daily_collection.py | 92 / 15 | cycle·실제 완료일 분리, 유효기간/승인/극성별 근거 집계 |
| management/commands/run_tag_collection_scheduler.py | 10 / 1 | queue/backpressure·tick·poll 시간 |
| management/commands/summarize_collection_metrics.py | 67 / 0 | 허용된 숫자 이벤트만 날짜·component별 집계 |
| services/bounded_collection_planner.py | 32 / 3 | planner 경로·후보 제외 사유·단계별 개수 |
| services/collection_telemetry.py | 71 / 0 | 숫자 이벤트·실제 대기·planner wrapper |
| test_bounded_collection_telemetry.py | 105 / 0 | bounded 계측·checkpoint 통합 회귀 |
| test_collection_telemetry.py | 258 / 0 | 시간/날짜/근거 품질/이벤트 집계 회귀 |

총 716행 추가·25행 삭제다. models/settings/migration/collection_resources/recovery는 master 원본이며 기존 CPU 자원 제한 기반을 다시 커밋하지 않는다. 대화·identity·검색 진단·수집 결핍 우선순위·웹/앱 UI 변경도 포함하지 않는다. runtime 검색 A v3 패키지를 적용하지 않았다.

worker의 `claim_next_job`, `settle_quota`, `claim_heartbeat` 세 함수는 master와 AST가 동일하다. 기존 quota 예약 날짜·한 번 정산·heartbeat·소유권 fencing·durable checkpoint 기반을 보존하고 계측을 연결한다. checkpoint에 작은 시간 메타데이터를 추가하며 새로운 schema를 만들지 않는다.

이전 공유 dirty snapshot 병합의 T1 충돌 3파일은 master 기반의 선별 차이로 후보를 구성해 제거했다. master 대비 patch의 별도 index 적용 검사, 변경 Python 9파일 AST 검사, diff whitespace 검사를 통과했다. 전체 dirty snapshot이나 충돌 마커가 있는 merge-tree 결과를 후보로 사용하지 않았다.

## 검증 범위

고정 후보 backend만 별도 폴더에 추출했다. Python 3.12.14·Django 6.0.5와 기존 로컬 검사 dependency를 사용했다. dotenv 로딩을 차단하고 DB가 메모리 SQLite임을 확인한 뒤 다음 모듈을 실행했다.

- recommendations.test_collection_telemetry
- recommendations.test_bounded_collection_telemetry
- recommendations.test_collection_resources
- recommendations.test_daily_tag_collection
- recommendations.test_report_daily_collection

checkpoint 실패 후 자정 이월 재개·외부 재호출 방지·단일 quota 정산, 원래 예약일 유지, 소유권 상실 차단, planner 계측 중복 방지, 유효/만료·승인/미승인 근거 분리, 실제 대기와 이벤트 종료일 집계, 허용 숫자만 로그 요약하는 회귀가 포함된다. 외부 수집 API나 실제 데이터는 사용하지 않았다.

제외된 7개는 PostgreSQL timeout/제한 복원·planner backoff·큰 합성 registry·0032 보존·별도 연결 heartbeat·skip_locked 검사다. [이전 PostgreSQL 검증](COLLECTION_POSTGRES_VALIDATION_2026-10-13.md)은 공유 통합본의 해당 7개 통과 기록이며 이 격리 후보에서 새로 실행한 결과는 아니다. 해당 임시 PostgreSQL 바이너리/압축파일이 정리된 상태여서 이번에는 다시 설치하거나 클러스터를 기동하지 않았다. 실제 PostgreSQL에서 이번 tree가 94개 모두 통과했다고 주장하지 않는다.

일보 조회와 worker의 추가 품질 조회·로그 출력 비용, 운영 부하/처리량·실제 근거 생성률은 이번 합성 회귀로 검증하지 않았다. 이벤트 기간 합계는 종료일에 귀속하므로 자정에 걸친 시간을 날짜별로 나눠 추정하지 않는다. 운영 배포/계측 완료와 분리한다.

## 증거와 보존

- [master→후보 patch](../runtime/t1-master-candidate-20261013/change.patch)
- [고정 manifest·9파일 hash·CPU 함수 대조](../runtime/t1-master-candidate-20261013/manifest.json)
- [검사·공유 소스 보존 audit](../runtime/t1-master-candidate-20261013/checks.json)
- [검사 출력](../runtime/t1-master-candidate-20261013/tests.txt)
- [병합된 원본 backend](https://github.com/binkim00/life-infra-map/tree/8291766f16a8bcc8928fe69f2f587bbbe00a57f1/backend)

검사 전후 공유 backend/frontend/mobile/deploy/shared 소스 hash 변경0, 공용 index hash 유지·staged0·HEAD `6f1f8323` 유지다. 본 검증 문서와 Git 상태 milestone만 갱신한다. 운영 서비스/환경/DB·migration 실행·배포·스토어 변경은 없다.

**다음 한 가지 행동:** 검토된 T1 고정 tree를 독립 커밋·draft PR로 준비한다. 이번 요청에서는 commit/push/PR을 실행하지 않았다.


### T1 독립 커밋 업로드·draft PR #6 생성 완료

사용자가 검토된 T1 고정 tree의 독립 커밋·draft PR 진행을 승인했다. master `84e3ebf780d4cb53041c8721b929c5a52bd0fccd` 부모에 tree `c70e09152b93db3d5bfa2d60c6577cc70c3ed9b0` 그대로 독립 commit `8291766f16a8bcc8928fe69f2f587bbbe00a57f1`을 기록했다. 별도 bare 저장소와 create-only empty expected-ref lease로 `codex/collection-p0-telemetry`를 업로드했다. 원격 비교에서 ahead1/behind0·정확히9파일·716추가/25삭제를 확인했다. 공유 index를 사용하거나 현재 branch를 이동하지 않았다.

[Draft PR #6](https://github.com/binkim00/life-infra-map/pull/6)을 생성·채팅에 연결했고 재조회 open/draft/merged=false·mergeable=true, 고정 head/base·1commit/9files 유지를 확인했다. 생성 직후 mergeable=false 응답은 재조회 true로 확정됐다. 검토와 관련87통과/PG7제외·기존CPU 함수 보존·운영 비용 미검증을 PR 본문에 기록했다. 검토된 tree가 바뀌지 않아 동일 로컬 검사를 반복 실행하지 않았다.

고정 head의 PR CI [38347194210](https://github.com/binkim00/life-infra-map/actions/runs/38347194210)은 첫 조회 in_progress/conclusion=null이다. 아직 성공으로 판단하지 않고 지속 polling하지 않는다. 반환된 테스트 merge SHA `9b3b202a1b6bcd3c63a571474bd014e8955bc69a`는 실제 master 병합 결과가 아니다. 공유 HEAD/index 유지·staged0, 실제 운영 배포·서비스/설정/DB·migration·스토어 변경 없음.

**다음 한 가지 행동:** PR #6 고정 head/base의 CI 완료 결과와 job별 범위를 확인해 병합 검토에 기록한다.


### PR #6 고정 CI 검토·원본 이력 유지 master 병합 완료

사용자가 CI/job별 범위 확인 후 원본 이력 유지 병합과 원격 반영 확인을 승인했다. PR head `8291766f16a8bcc8928fe69f2f587bbbe00a57f1`, base `84e3ebf780d4cb53041c8721b929c5a52bd0fccd`, 1커밋/9파일/716추가25삭제 및 mergeable=true가 유지됨을 확인했다. [PR CI38347194210](https://github.com/binkim00/life-infra-map/actions/runs/38347194210)은 completed/success다. Code Review headRevision과 각 check head_sha가 고정 head와 일치한다.

| Job / ID | 고정 workflow와 실행 step으로 확인한 범위 | 결과 |
|---|---|---|
| Django / 115131225189 | Python3.12, requirements 설치, accounts/boards/recommendations, config.test_settings | success |
| Spring / 115131225242 | Java21, Gradle test --no-daemon | success |
| 웹 / 115131225065 | Node24, npm ci/test/production build | success |
| 앱 코드 / 115131225295 | Node24, npm ci, TypeScript/lint/Node tests | success |

네 job의 모든 실행 단계가 success이며 개별 annotation 네 개는 ubuntu-latest 실행 이미지 변경 notice다. 같은 head의 다른 push run38347145240 check 네 개도 success로 조회됐지만 이번 job별 상세 범위는 PR run38347194210 기준이다. 실제 PostgreSQL 잠금/heartbeat/SQL timeout, 앱 test:ux/native build·운영 부하/배포는 이 CI에 포함되지 않는다. 테스트 개수·환경 skip 통과를 step 성공으로 추정하지 않았다. 로컬87통과/PG7제외는 별도 증거이며 이전 공유본PG7성공으로 이 한계를 지우지 않는다.

검토를 PR 본문에 기록한 뒤 draft를 ready로 전환하고 expected_head_sha를 고정해 merge commit 방식으로 병합했다. GitHub merged=true, merge SHA `9ab7e232ddb9049210caaad9e384a09a76084b08`. 재조회 PR closed/merged=true, merged_at 2026-10-13 13:38:26 KST 및 원격 master의 같은 tip을 확인했다. 원본 head→master 비교는 merge-base가 원본 `8291766f`, ahead1/behind0·파일 차이0이다. 따라서 원본 독립 커밋이 master의 조상으로 유지되고 검토한 소스가 그대로 반영됐다. 이전 테스트 merge SHA9b3b202a와 실제 병합 SHA를 구분한다.

공유 HEAD `6f1f8323`·공용 index hash·staged0을 보존했다. 현재 checkout에서 원격 master를 pull/checkout하지 않았다. 실제 운영 배포·서비스/설정/공유 DB·migration 실행·스토어 변경은 없다. post-merge push CI와 실제 profile 잔디 화면은 이번 PR CI/원격 반영으로 대체하지 않는다.

**다음 한 가지 행동:** 새 master `9ab7e232` 기준 최신 공유 미커밋을 다시 비교해 T1 포함분을 제외하고 잔여 독립 후보를 갱신한다.
