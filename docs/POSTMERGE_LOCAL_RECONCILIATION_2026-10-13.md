# master745ef652 병합 후CI·공유 미커밋 재정리 — 2026-10-13

## 병합 후CI

[push CI38349851893](https://github.com/binkim00/life-infra-map/actions/runs/38349851893)은 master `745ef65227546ac06754ab07c1287527c32792f4`에서 실행된 run25다. event=push·head_branch=master·head_sha 일치·completed/success를 직접 확인했다. 14:08:02KST 시작, 14:09:03KST updated 기록이며 PR8 CI와 다른 실행이다. head tree는 검토된 cb604d5d와 일치한다.

| Job / ID | 실제 실행 범위 | 결과 |
|---|---|---|
| Django /115139513566 |Python3.12·requirements설치·accounts/boards/recommendations/config.test_settings|success|
| Spring /115139513612 |Java21·Gradle test --no-daemon|success|
| 웹 /115139513348 |Node24·npm ci/test/production build|success|
| 앱 /115139513578 |Node24·npm ci·TypeScript/lint/Node tests|success|

각job의head_sha는745ef652이고모든실행단계가success다. 실제PG/native/mobileUX/실기기·운영처리량/배포를이CI에서확인했다고확대하지않는다. 기존별도로컬회귀결과는이전통합보고서범위로유지한다. 개별annotation은이번push에서추가조회하지않았고PR8annotation과동일하다고추정하지않았다.

PR기반CI도구는다른head인최종master를지정하면409를반환한다. 또한commit workflow wrapper는PR-triggered run만조회한다. 따라서승인된GitHub 읽기전용fetch로event=push/head_sha 조건과실제jobsJSON을확인했으며PRCI성공을병합후CI로대체하지않았다. [CI 증거](../runtime/postmerge-master-ci-20261013.json)에필요한metadata/steps만보존했다.

## 최신 공유변경 분류

원격master는이번조회에서도745ef652다. 공유checkout은이전 HEAD6f1f8323를유지한다. master와blob비교시CRLF/LF는Git clean 변환기준으로정규화했다. 새비교자료는 [audit](../runtime/postmerge-local-reconciliation-20261013/audit.json)이다.

| 코드·설정·검사 분류 | 파일 | 판단 |
|---|---:|---|
| master와현재내용까지동일 |131|재커밋제외|
| 기존통합의보존결정에따른내용차이 |15|새미반영기능으로분류하지않음|
| 통합이후변경된/추가된코드 |2|N1 신규검토후보|
| 합계 |148|이전147보다신규검사파일1개증가|

옛HEAD대비 tracked변경102개·runtime제외untracked80개가스냅샷에존재했다. 이총182개는코드148/문서29/디자인5다. 별도새본문서생성으로로컬문서는30개,untracked81개가된다. 코드수는변하지않는다. runtime14,308개·디자인5개는기본제외다. ignored 빌드산출물은이count에포함하지않는다.

131개와15개는모두이전통합의범위/중복분이다. 15개는현재파일그대로재적용하면master문구·기존회귀·계약을되돌리거나추가검사를지울수있는차이이므로남은개발76개로세지않는다. 실제shared파일을master로덮어쓰거나공용index/checkout을전환하지않았다.

### 보존결정에 따른15개 차이

| 경로 | master 보존·통합 내용 |
|---|---|
|`backend/config/settings.py`|master의 IS_TESTING 위치·기존 CPU 설정 보존|
|`backend/recommendations/serializers.py`|master의 기존 응답 계약과 새 공개 제보 serializer 결합|
|`backend/recommendations/services/search_hard_gate.py`|master 기존 엄격 조건 처리와 잔여 조건 변경 결합|
|`backend/recommendations/test_general_search_contract.py`|master 기존 회귀 검사 보존|
|`backend/recommendations/test_mobile_admin_workflows.py`|master 기존 제보/관리자 회귀와 공개 응답 검사 결합|
|`backend/recommendations/tests.py`|master 기존 검사 보존; 오래된 공유 파일로 되돌리지 않음|
|`backend/recommendations/views.py`|master 기존 endpoint/응답 계약과 대화·진단·공개 제보 변경 결합|
|`deploy/gateway/Dockerfile`|master 기존 build 단계와 shared COPY 결합|
|`frontend/src/views/AdminOperationsView.jsx`|master의 사용자 문구·한국어 상태 표시 유지|
|`frontend/src/views/LoginView.jsx`|master 기존 로그인 UI·메시지와 safe-error 변경 결합|
|`frontend/src/views/MapSearchView.jsx`|master 카테고리 helper와 새 검색/메시지 import 결합|
|`frontend/src/views/MypageView.jsx`|master 기존 MY 표시와 사용자 메시지 변경 결합|
|`frontend/src/views/home/PlaceResultList.jsx`|master 카테고리 helper와 canonical placeKey 결합|
|`mobile/README.md`|master는 공개된 출시 준비 문서로 링크 보완; 로컬은 별도 보고서 링크 유지|
|`mobile/tests/ux/account-deletion.test.jsx`|master만 경합 회귀2개와 import 순서 정리 추가; 로컬은 기존3개 유지|

### N1 신규미반영 — 게시글 사진 제거와QA회귀2파일

- `mobile/src/components/post-editor.tsx`: 통합시점에는master와동일했으나현재추가수정됐다. 사진제거를setImage(null)만하던동작에서선택사진을보관한뒤UI를비우고removeDraftImages([removed])를호출한다. master 대비 7행 추가·1행 삭제의새기능차이다.
- `mobile/tests/ux/audit-20261013.test.jsx`: master에없는신규파일이며모의API/저장소로게시글상호작용초안재마운트·계정격리,PostEditor 사진제거의관리파일삭제호출을검사하는2개case를포함한다.

현재sourcehash를기존통합snapshot과대조해1개수정·1개신규임을확인했다. 기존보고서의최초사진제거실패와현재수정본은시점이다르므로보고서결과를현재2파일의검사성공으로승격하지않았다. 이번요청은조회·분류이며이2파일의격리후보생성/검사/commit/push/PR은하지않았다. 다른작업의진행중변경으로보존한다.

### 로컬문서와증거

스냅샷29개는master에없는검증/통합/검색·수집·모바일상태문서와역사적patch다. 이번보고서1개를더하면30개다. 이는신규기능2파일과구분한문서커밋검토후보이며내용최신화·중복통합·게시범위확인없이일괄올리지않는다. CODEX_STATE는기존관리방식대로별도상태문서이고이Gitinventory의ignored파일count에는들어가지않는다.

- `docs/COLLECTION_LIMITED_OBSERVATION_PLAN_2026-10-13.md`
- `docs/COLLECTION_OPERATION_START_BASELINE_2026-10-13.md`
- `docs/COLLECTION_P0_DEPLOYMENT_CANDIDATE_2026-10-13.md`
- `docs/COLLECTION_P0_RELEASE_2026-10-13.md`
- `docs/COLLECTION_POSTGRES_VALIDATION_2026-10-13.md`
- `docs/COLLECTION_QUALITY_FOLLOWUP_2026-10-13.md`
- `docs/COLLECTION_TELEMETRY_INTEGRATION_2026-10-13.md`
- `docs/COLLECTION_TELEMETRY_P0_2026-10-13.md`
- `docs/GIT_INTEGRATION_PLAN_2026-10-13.md`
- `docs/M2_MASTER_CANDIDATE_REVIEW_2026-10-13.md`
- `docs/MOBILE_APK_INSTALL_VERIFICATION_2026-10-13.md`
- `docs/MOBILE_FULL_QA_2026-10-13.md`
- `docs/MOBILE_INTEGRATION_REVIEW_2026-10-13.md`
- `docs/MOBILE_STORE_READINESS_2026-10-13.md`
- `docs/NAVER_PLACE_EVIDENCE_SEARCH_COMPARISON.md`
- `docs/REMAINING_INTEGRATION_REVIEW_2026-10-13.md`
- `docs/SEARCH_CONVERSATION_QUALITY_REPORT.md`
- `docs/SEARCH_EVIDENCE_PIPELINE_COMPLETION_2026-10-06.md`
- `docs/SEARCH_EVIDENCE_VALUE_DIAGNOSIS_2026-10-06.md`
- `docs/SEARCH_HYDRATION_REPEAT_REVIEW_2026-10-13.md`
- `docs/SEARCH_PACKAGE_A_REVALIDATION_2026-10-13.md`
- `docs/SEARCH_PACKAGE_A_VALIDATION_2026-10-13.md`
- `docs/SEARCH_PIPELINE_RELEASE_REVIEW_2026-10-13.md`
- `docs/SEARCH_PREPARED_EVIDENCE_REVIEW_2026-10-13.md`
- `docs/SEARCH_SEOUL_SQL_TAIL_REVIEW_2026-10-13.md`
- `docs/SEARCH_UX_COMPLETION_REPORT.md`
- `docs/T1_MASTER_CANDIDATE_REVIEW_2026-10-13.md`
- `docs/operations/collection-telemetry-bounded-76e2.patch`
- `docs/operations/collection-telemetry-resource-76e2.patch`
- `docs/POSTMERGE_LOCAL_RECONCILIATION_2026-10-13.md` (이번보고서)

## 보존·완료범위

스냅샷중파일hash변경0·문서기록직전코드hash유지·공유HEAD/index hash유지·staged0·tracked diffcheck통과다. 이번작업은Git읽기·runtime전용비교object·문서milestone만변경했다. 실제계정삭제·운영배포/서비스/설정/DB/migration/스토어변경·새commit/push/PR은없다.

병합후CI확인과최신분류는완료했다. **다음한가지행동:** 신규N1 2파일만745ef652위에격리후보로구성하고사진제거/초안모의회귀와관련코드검사를확인한다.
