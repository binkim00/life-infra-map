# P0 선별 배포 후보와 되돌리기 절차

**로컬 소스 후보·배포/되돌리기 절차 준비 완료. 운영 실행은 하지 않았다.** 실제 이미지 빌드·검증·worker 종료 안전성 확인이 남아 있어 즉시 배포 가능한 상태라고 판단하지 않는다. 이 문서는 배포/서비스 중지/되돌리기 실행 승인이 아니다.

## 고정한 후보

| 항목 | 식별자·범위 |
|---|---|
| 검토된 P0 원본 커밋 | `8291766f16a8bcc8928fe69f2f587bbbe00a57f1` |
| 검토 tree | `c70e09152b93db3d5bfa2d60c6577cc70c3ed9b0` |
| 검토/병합 | [PR #6](https://github.com/binkim00/life-infra-map/pull/6), 병합 SHA `9ab7e232ddb9049210caaad9e384a09a76084b08` |
| 운영 CPU 기준 | `76e2de2f9b30ad096022197dd946138d2a52668f` |
| 되돌릴 이미지(13:37 관측) | `sha256:19753ab879653d630e3ec431ffda96058f8efe0e0c01af26b70223ec1ff16824` |
| 배포 대상 | 기존 `life-infra-map-tag-worker`, `life-infra-map-tag-scheduler` 각각 1개 |

GitHub 원격 비교를 이번에 읽기 전용으로 확인했다. 원본 커밋은 현재 master의 merge-base이며 ahead 1/behind 0·파일 차이 0이었다. 공유 checkout을 pull/전환하거나 원격 ref를 변경하지 않았다.

검토 base `84e3ebf7`의 backend Git tree와 운영 CPU 기준 backend tree가 정확히 같다. CPU→후보 backend 차이는 아래 9파일·716행 추가/25행 삭제뿐이다. 공유 dirty backend가 아니라 고정 Git blob으로 패키징했다.

- management/commands: plan_daily_tag_collection.py, process_place_tag_collection_jobs.py, report_daily_collection.py, run_tag_collection_scheduler.py, summarize_collection_metrics.py
- services: bounded_collection_planner.py, collection_telemetry.py
- tests: test_bounded_collection_telemetry.py, test_collection_telemetry.py

models/settings/migration/collection_resources/recovery/requirements/Dockerfile 및 검색·웹·앱·API·DB 서비스는 변경 대상이 아니다. 새로운 migration을 실행하지 않는다. worker의 claim_next_job/settle_quota/claim_heartbeat는 운영 CPU 원본과 AST 동일함을 이번 후보에서 재확인했다.

## 로컬 후보 꾸러미

위치는 `runtime/collection-deployment-candidate-20261013/`이다.

| 산출물 | 용도 |
|---|---|
| image-context.tar.gz / image-context/ | 검토된 9개 Git blob과 COPY 전용 Dockerfile. 실제 이미지 제작의 제한된 context |
| manifest.json | commit/tree·파일 SHA256·CPU 함수 AST·산출물 SHA256·미완료 조건 |
| cpu-to-p0.patch | CPU 기준→P0의 검토용 차이. 운영 디렉터리에 직접 patch하지 않음 |
| p0-to-cpu-reference.patch | 역방향 소스 참고. 운영 되돌리기는 기존 이미지로 교체 |
| candidate-backend.tar.gz | 고정 backend 소스 참고 사본 |
| rollback-source-reference.tar.gz | 고정 CPU backend 소스 참고 사본. 이전 실행 이미지를 대체하는 배포 산출물이 아님 |
| image-only.override.yml | 기존 Compose 위에 두 수집 서비스의 image만 지정하는 후속 실행용 template |

빌드 context에는 env·데이터·의존성 설치 과정이 없다. 참고 backend archive는 `.env`/`.env.*` 이름을 제외했고 LFS pointer를 그대로 보존하므로 이것을 완전한 데이터 복원/새 빌드 꾸러미라고 해석하지 않는다. 실제 배포 후보는 9파일 COPY context다.

Git blob과 Windows 검토 폴더의 CRLF 차이는 LF 정규화 후 동일함을 확인했다. archive는 Git 원본 byte를 사용하며 그 SHA256을 manifest에 별도 기록했다. 검토 폴더 hash와 archive hash가 다르다는 이유로 임의 파일을 선택하지 않는다.

image-context.tar.gz SHA256: `3a49ddd8ecba2e018d128c0928e69fa186d7f7be284dabe02403e100d88dc1ad`.

## 이미지 제작과 배포 전 통과 조건

기존 CPU 이미지에 9파일만 COPY하는 파생 이미지를 만든다. 의존성 설치·floating Python base pull을 반복하지 않아 기존 Python 3.13/라이브러리와 CPU 기반을 유지한다. 기존 이미지가 남아 있다는 직접 확인은 배포 직전에 필요하다. 13:37 기록을 현재 가용성 증거로 대체하지 않는다.

후속 실행에서 기존 image ID를 전용 로컬 태그에 연결하고, manifest와 일치하는 context로 network none/pull false 빌드한다. 이 태그는 빌드용 alias이며 최종 배포/되돌리기는 확인된 image ID로 고정한다. 파생 이미지에는 원본 P0 commit revision label을 넣는다. Dockerfile에는 COPY만 있으며 컨테이너 안에서 DB/API 명령을 실행하지 않는다.

아래 조건을 모두 만족하기 전에는 서비스 교체를 시작하지 않는다.

1. **후보 자체의 PostgreSQL 검증:** 검토 고정 후보 87개 SQLite 통과/PG 7개 제외와 기존 공유 통합본 PG 7개 통과를 구분한다. 같은 후보 Git blob으로 격리 PG 7개를 직접 검사하거나, 기존 통과본과 관련 코드·의존성이 동일하다는 검토 가능한 증거를 확보해야 한다. 현재는 이 후보 직접 PG 실행 증거가 없다.
2. **실제 파생 이미지 검증:** Python 3.13 실행·dependency import·env 없는 격리 system check/관련 회귀·9파일 hash·CPU 함수 AST·기존 비대상 앱 파일 유지·revision label 확인. 이미지 검증에서 운영 env/DB를 연결하지 않는다. 이미지 ID와 결과를 manifest에 추가한 후 불변 ID로 고정한다.
3. **종료 안전성 검증:** 현재 worker는 watch 중 신규 claim을 잠시 막는 drain 옵션과 명시적 SIGTERM handler가 없다. processing=0 조회 직후에도 새 claim이 가능하므로 그것만으로 안전한 종료를 보장하지 않는다. 합성 데이터 환경에서 승인된 종료 방법이 신규 claim 차단·진행 중 collector/checkpoint/materialization 처리에 어떻게 작용하는지 확인해야 한다. 이 조건이 해결되지 않으면 배포를 보류한다.
4. **최신 기준선/복구 준비:** 운영 image ID/revision/schema·worker 1개·bounded/pacing·기존 env/Compose/network·quota/lease·경보를 제한 읽기로 확인한다. 이전 이미지의 로컬 가용성과 prune 대상 제외를 확인하고 보호한다. env 값·비밀을 반출하지 않는다. 복구 책임자·복구 시간 한도·안전한 중지 방법을 확정한다.
5. **구체적 실행 승인:** 빌드/서비스 교체/중단·되돌리기 범위와 검증된 이미지 ID가 제시된 뒤 별도 배포 승인을 받아야 한다. 본 요청은 후보 준비 범위다.

이미지 내부 검증 및 종료 방법 확인은 이번에 실행하지 않았다. 공개 CI 성공은 이미지 실행·운영 부하 검증을 대체하지 않는다.

## 승인 이후의 배포 순서

1. 기존 운영 Compose/env/network 파일을 그대로 사용하는 경로를 확정한다. override는 image만 덮는다. `config --quiet`만 검증하고 전체 config/env를 출력하지 않는다. `.env` 복사·새 settings 작성·migration·schema 초기화는 하지 않는다.
2. 기존 CPU 이미지 가용성과 복구 identity를 다시 확인한다. 시작 quota·예약/미정산 checkpoint·처리 중 작업·CPU/경보를 기록한다. 이미 다른 revision이 실행 중이면 과거 CPU image를 자동 복구 대상으로 선택하지 않고 중단해 재검토한다.
3. 검증된 quiescence/종료 방식으로 신규 claim을 막고 worker를 교체한다. 최초 적용은 기존 worker 하나만 교체하고 CPU scheduler는 유지한다. 추가 replica/수동 finite worker/작업 계획/priority·quota 변경으로 표본을 만들지 않는다.
4. 운영 image ID·9파일 hash·revision label·DB schema 유지와 worker 1개를 확인한다. 자연 작업이 있을 때 P0 worker_attempt/worker_checkpoint 숫자 이벤트·단계 시간·원래 예약일·단일 정산을 확인한다. 활동이 없으면 `미관찰`로 남긴다. marker 파일의 존재를 실제 이벤트 발생으로 대체하지 않는다.
5. worker 검증과 자원 조건이 충족되면 기존 scheduler 하나를 같은 이미지로 교체한다. planner/scheduler_queue·refill/scan/backpressure·CPU 제한과 설정 유지 여부를 확인한다. 두 서비스 교체가 끝나기 전에는 혼합 revision 기간의 이벤트를 별도 표시한다.
6. [제한 관찰 계획](COLLECTION_LIMITED_OBSERVATION_PLAN_2026-10-13.md)의 주간 최대30분/attempt100개를 수행한다. 자정 경계 관찰은 별도 예정 구간에서 수행하며 자동 예약하지 않는다. 실제 기준선·중단 기준·결측을 기록한 뒤 확대 여부를 판단한다.

후속 Compose 실행의 형태는 기존 파일 + image-only.override.yml, `up -d --no-build --pull never --no-deps`와 정확한 서비스 이름이다. 실제 호출에는 검증된 경로·이미지 ID·종료 방식이 들어가야 한다. 전체 `up --build`, `down`, `down -v`, DB/API 서비스 교체, 최신 master 자동 pull은 사용하지 않는다.

## 중단·되돌리기 판단

**관찰 중단과 서비스 되돌리기는 다른 행동이다.** 읽기 SQL timeout/자료 부족/관찰 입력 한도 도달은 관찰을 끝내는 사유이며 자동 rollback 사유가 아니다. 아래 배포 실패는 승인된 복구 범위에서 서비스 교체를 중단하고 CPU 이미지 복귀를 판단한다.

- 실제 후보 image ID/revision/file hash가 manifest와 불일치하거나 worker/scheduler 수·bounded/pacing·CPU 제한 설정이 달라짐
- 새 restart/OOM/import 오류, 기존 서비스 경보 ALARM, 5분 평균 CPU80% 이상 1구간 또는50% 이상 2연속 구간 등 계획의 자원 조건 발생
- 직접 확인한 중복 정산·예약일 변경·실제 요청 절단·소유권 fencing 실패·정산 완료 checkpoint의 외부 재호출
- 정상 처리 중 지속 heartbeat 갱신 중단·checkpoint 손상 또는 새 계측이 처리 실패를 유발함

이벤트가 없을 때는 먼저 자연 작업·해당 시점·revision을 대조한다. 무활동 구간의 이벤트 0만으로 rollback하지 않는다. 품질 수율 저하도 표본/기간을 확인하며 무근거로 설정을 완화하지 않는다.

## 되돌리기 순서와 데이터 보존

1. 승인된 중지 방식으로 신규 계획·claim을 막는다. 실패 시각과 숫자 이벤트, 작업 상태·quota·원래 예약일·정산 표식·checkpoint 유무를 제한 읽기로 보존한다. checkpoint 원문이나 collector 응답을 반출하지 않는다.
2. 마지막 작업의 lease와 실제 외부 호출 진행 여부를 확인한다. 강제 종료로 collector 호출 성공→checkpoint 저장 이전 구간을 잃으면 외부 재호출을 완전히 방지할 수 없다. 이 위험을 없다고 주장하지 않으며 확인되지 않으면 담당자의 장애 절차로 넘긴다. SIGKILL이나 즉석 job/quota 수정으로 해결하지 않는다.
3. 두 서비스 image를 확인된 이전 CPU image ID로 고정한다. 먼저 worker를 이전 이미지로 복귀시키고 검증한 다음 scheduler를 복귀시킨다. 배포 실패 단계에서 scheduler가 아직 CPU이면 불필요하게 교체하지 않는다. 설정·네트워크·worker ID·replica 수는 기존 값 유지다.
4. **schema와 업무 데이터는 되돌리지 않는다.** migration0032 제거, `migrate ...0031`, 예약/요청 수 차감, Evidence 삭제, checkpoint/telemetry 초기화, 작업 상태 강제 reset을 하지 않는다. 역 patch는 실행 컨테이너에 적용하지 않는다.
5. P0 checkpoint의 `_collection_telemetry`는 작은 추가 metadata이며 CPU quota/claim/heartbeat 계약을 바꾸지 않는다. 다만 실제 CPU reader가 이 checkpoint를 무호출 재개하고 한 번 정산하는 호환성은 종료 검증과 함께 합성 환경에서 확인해야 한다. 구형 코드로 돌아가면 추가 telemetry가 이어서 유지되지 않을 수 있어 이벤트/행 통계의 기간을 분리한다.
6. 복귀 image ID/revision·running/restart/OOM·worker1·기존 설정·CPU/경보·기존 schema를 직접 확인한다. 자연 작업이 있으면 처리/정산/heartbeat를 확인하고 없으면 미관찰로 남긴다. 되돌린 후 task별 stats·Evidence·quota 누적 결과를 원상복구했다고 주장하지 않는다.

관찰 자료는 유지하며 P0 재배포는 원인 확인·검증을 거친 별도 결정이다. 이전 이미지가 없거나 최신 운영 기준과 다르면 source reference로 즉석 재빌드해 동일 이미지라고 간주하지 않고 복구 차단으로 보고한다.

## 이번 검증과 남은 조건

이번에는 고정 후보/CPU backend tree 동일 기반·정확한9파일 차이·검토 사본과Git 원본 LF 동일성·Python AST·CPU 세 함수 AST 보존·archive 내용/파일 hash·원격 master 원본 이력 포함을 확인했다. 같은 검토 tree이므로 이미 완료한 87개 회귀와 CI를 반복하지 않았다. [검토 기록](T1_MASTER_CANDIDATE_REVIEW_2026-10-13.md)의 범위/PG7 제외와 [운영 시작 기준선](COLLECTION_OPERATION_START_BASELINE_2026-10-13.md)을 구분한다.

빌드 image ID, 실제 후보 PG 검사, 종료/CPU checkpoint 호환성, 운영 부하와 승인된 배포·복귀 실측은 미완료다. 현재 후보는 검토 가능한 소스 꾸러미이며 운영 반영 완료가 아니다.

보존 audit는 관련 기존696파일 중694개 동일·HEAD/index 유지다. 다른 채팅에서 변경한 GIT_INTEGRATION_PLAN과 MOBILE_APK_INSTALL_VERIFICATION 보고서2개는 이 채팅에서 쓰지 않았으며 최신 상태를 보존했다. 공통 CODEX_STATE에는 이번 milestone만 추가했다.

다음 한 가지 행동: 별도 요청 시 운영 연결 없는 격리 환경에서 이 고정 후보의 PostgreSQL·종료/CPU checkpoint 호환성 검증을 준비·실행한다.
