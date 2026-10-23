# Git 통합 준비안 — 2026-10-13

## 결론과 확인 범위

대상 저장소: [binkim00/life-infra-map](https://github.com/binkim00/life-infra-map), 기본 브랜치 `master`. 이번 작업은 Git 이력·문서 조사와 격리 충돌 검사다. 기능 코드, 현재 checkout, 공용 index, 원격 refs, 운영 서비스·설정·데이터를 변경하지 않았다. 공유 작업의 소유권을 추정해 커밋하지 않았다.

10월 13일 GitHub connector로 기본 브랜치와 원격 네 브랜치 tip을 직접 조회해 로컬 remote-tracking refs와 일치를 확인했다. 터미널 `ls-remote`는 DNS 오류였으며 fetch 성공으로 표현하지 않는다. 저장소는 public이고 merge/squash/rebase는 허용, auto-merge는 비활성이다. 보호 규칙의 과거 부재 기록은 현재 확인으로 재사용하지 않는다.

## 브랜치 관계: 공통 이력은 한 번만 계산

| ref | 고정 SHA | master 대비 커밋 | 의미 |
|---|---|---:|---|
| `master` | `ff4560695b134b4ed8c1ce17047d8526c97d4ae2` | 0 | 기본 브랜치 |
| `origin/codex/disk-maintenance` | `c734d66e7e6ae790384c777e186081a067e14d9d` | 30 | 원격 disk |
| `HEAD` | `6f1f8323cc87e3def055905a69e44c3af8322221` | 39 | 현재 로컬 disk |
| `origin/codex/release-foundation` | `5550de6532ae014ec6cbf923ebc0659097e1a2c2` | 69 | 원격 출시 기반 |
| `origin/codex/collection-resource-budget` | `76e2de2f9b30ad096022197dd946138d2a52668f` | 74 | 원격 수집 제한 |
| `codex/service-flow-verification` | `7d5b9a016ca362e07bc344c76fae237e86e0fe9c` | 54 | 로컬 Android 검증 |
| `codex/release-infra` | `c33eb397d0ce81faf8b3308f0b1d3d2b1837aa57` | 47 | 로컬 수동 배포 도구 |

포함 경로는 `master → origin/disk(30) → 현재 disk(추가 9) → release-foundation(누적 69) → collection-resource-budget(추가 5, 누적 74)`다. `service-flow-verification`의 54개 커밋은 release-foundation에 전부 포함돼 있다. 로컬 disk의 9개 커밋도 release-foundation과 collection의 원격 이력에 **같은 SHA로 이미 존재**한다. disk 원격 ref가 뒤처진 것이며 프로젝트 전체에서 미업로드된 9개라고 해석하면 안 된다.

`release-infra`는 `bef1592ed08ac9cc9968a7474c3279269953269e`를 출시 기반과 공유하고 `c33eb397` 한 개만 collection 바깥에 있다. collection과 infra의 좌/우 고유 커밋은 28/1이다. 따라서 기존 이력의 통합 대상은 collection의 74개 + infra 고유 1개 = **원본 고유 커밋 75개**다(향후 merge commit 제외). disk 30 + release 69 + collection 74를 합산하지 않는다.

7개 ref의 21쌍에 대해 merge-base·ancestor·좌우 개수를 검사하고 `--cherry-mark --no-merges`로 갈라진 이력의 patch 동등성을 확인했다. 다른 SHA의 동등 patch 표식은 0개다. 같은 조상으로 이미 포함된 커밋과 부분적으로 가져온 미커밋 hunk는 이 값의 대상이 아니다. fix/ai-search-rerank-and-routing, kyb, practice 및 detached worktree는 이 요청의 통합 대상에서 제외하며 현재 보존한다.

## 현재 disk의 9개 커밋 검토

| SHA | 범위 | 독립성·처리 |
|---|---|---|
| `7d16b6b6` | RELEASE_READINESS 최초 | 이후 2개 문서 수정과 연속 문맥, 이력 보존 |
| `044ba66a` | 도메인 후보 문서 | 앞 문서의 수정, 별도 cherry-pick 불필요 |
| `0b9147e8` | 주소·비용 문서 | 같은 연속 문서 |
| `1292997e` | public-edge 3파일 + 준비 문서 | 공개 HTTPS 구성의 시작; 이후 수정까지 함께 리뷰 |
| `e19d42f4` | 주소 연결 상태 문서 | 운영 식별정보 포함 가능, 과거 증거로 읽기 |
| `d00bea54` | Caddy·README·준비/보안 문서 | 앞 구성의 bind·보안 헤더 후속; 앞 커밋과 함께 검토 |
| `1efd9a33` | 보안 검토 문서 | 앞 문서의 결과 확정 |
| `b40f0b27` | 준비 문서 + 스토어 체크리스트 | 체크리스트 생성 |
| `6f1f8323` | 체크리스트 후속 | 앞 체크리스트와 연속 |

각 커밋의 변경 경로와 해당 시점 전체 blob을 읽어 확인했다. runtime, 환경파일, APK/AAB, dump, 로그, 개인키 파일을 새로 포함한 커밋은 0개다. 개인키/일반 token/AWS 키/문자열 password·secret·token 패턴의 고신뢰 탐지 0개. 이 제한된 검사는 완전한 비밀·개인정보 감사가 아니다. 기존 공개 연락처·운영 식별정보가 있는 문서는 외부 공개 범위 검토가 필요하며 보고서에 원문을 복제하지 않았다. 9개 모두 이미 원격 조상으로 포함됐으므로 재커밋·cherry-pick·날짜 변경 없이 기존 SHA를 보존한다.

## 미커밋 스냅샷과 기능별 파일 목록

초기 snapshot: tracked 수정 79개, 압축된 untracked status 항목 32개. 이 보고서와 다른 채팅의 후속 문서가 추가되면 수치는 변한다. 아래는 해당 snapshot의 파일명이며 소유자 확정 목록이 아니다. runtime 폴더 한 항목은 내부 파일 수천 개를 숨기므로 status 항목 수를 파일 수로 오해하지 않는다.

M=tracked 수정, U=untracked. 테스트는 기능 코드와 함께 커밋해야 하고 아래 분류는 검토 편의를 위한 목록이다.

### 검색·대화·근거 및 공개 제보 API

- M `backend/config/settings.py`
- M `backend/recommendations/management/commands/analyze_identity_mismatches.py`
- M `backend/recommendations/serializers.py`
- M `backend/recommendations/services/ai_intent_planner.py`
- M `backend/recommendations/services/ai_search_orchestrator.py`
- M `backend/recommendations/services/ai_web_search_provider.py`
- M `backend/recommendations/services/bootstrap_priority.py`
- M `backend/recommendations/services/conversation_sessions.py`
- M `backend/recommendations/services/kakao_local.py`
- M `backend/recommendations/services/search_coverage_demand.py`
- M `backend/recommendations/services/search_hard_gate.py`
- M `backend/recommendations/services/tag_evidence_aggregation.py`
- M `backend/recommendations/views.py`
- U `backend/recommendations/management/commands/report_tag_promotion_queue.py`
- U `backend/recommendations/services/conversation_patches.py`
- U `backend/recommendations/services/external_place_identity.py`
- U `backend/recommendations/services/search_candidate_trace.py`
- U `backend/recommendations/services/search_pipeline_metrics.py`

### 테스트·검사 설정 — 해당 기능에 동반

- M `backend/recommendations/test_conversation_sessions.py`
- M `backend/recommendations/test_conversation_state_refinement.py`
- M `backend/recommendations/test_general_search_contract.py`
- M `backend/recommendations/test_mobile_admin_workflows.py`
- M `backend/recommendations/test_result_quality_fallback.py`
- M `backend/recommendations/test_search_coverage_demand.py`
- M `backend/recommendations/test_tag_evidence_aggregation.py`
- M `backend/recommendations/tests.py`
- M `frontend/src/api/recommendation.test.js`
- M `frontend/src/views/HomeView.test.jsx`
- M `frontend/src/views/MapSearchView.test.jsx`
- U `backend/recommendations/test_conversation_quality_flows.py`
- U `backend/recommendations/test_evidence_independence.py`
- U `backend/recommendations/test_external_place_identity.py`
- U `backend/recommendations/test_search_candidate_trace.py`
- U `backend/recommendations/test_search_pipeline_metrics.py`
- U `backend/recommendations/test_tag_promotion_queue.py`
- U `frontend/src/hooks/useNotifications.test.jsx`
- U `frontend/src/utils/searchUx.test.js`
- U `mobile/tests/ux/conversation.test.jsx`
- U `mobile/tests/ux/notifications.test.jsx`
- U `mobile/tests/ux/setup.jsx`
- U `mobile/vitest.ux.config.mjs`

### infra·빌드

- M `deploy/gateway/Dockerfile`

### 웹 UI·검색 상태·오류·알림

- M `frontend/src/api/recommendation.js`
- M `frontend/src/hooks/homeSearchState.js`
- M `frontend/src/hooks/useHomeSearch.js`
- M `frontend/src/hooks/useNotifications.js`
- M `frontend/src/hooks/useSavedPlaceActions.js`
- M `frontend/src/utils/aiWebSearchPolicy.js`
- M `frontend/src/utils/homePlaceHelpers.js`
- M `frontend/src/utils/kakaoPlaceRecommendation.js`
- M `frontend/src/utils/placeResultConverters.js`
- M `frontend/src/views/AdminOperationsView.jsx`
- M `frontend/src/views/AdminPlaceReportsView.jsx`
- M `frontend/src/views/BoardCreateView.jsx`
- M `frontend/src/views/BoardDetailView.jsx`
- M `frontend/src/views/BoardEditView.jsx`
- M `frontend/src/views/HomeView.jsx`
- M `frontend/src/views/InquiryCreateView.jsx`
- M `frontend/src/views/LoginView.jsx`
- M `frontend/src/views/MapSearchView.jsx`
- M `frontend/src/views/MapSearchView.module.css`
- M `frontend/src/views/MyInquiryView.jsx`
- M `frontend/src/views/MyPlaceReportsView.jsx`
- M `frontend/src/views/MypageView.jsx`
- M `frontend/src/views/PlaceReportView.jsx`
- M `frontend/src/views/PreferenceSettingsView.jsx`
- M `frontend/src/views/SearchHistoryView.jsx`
- M `frontend/src/views/home/AiWebSearchPanel.jsx`
- M `frontend/src/views/home/PlaceResultList.jsx`
- M `frontend/vite.config.js`
- U `frontend/src/hooks/useOverlayHistory.js`
- U `frontend/src/hooks/usePanelHistory.js`
- U `frontend/src/styles/SearchUx.css`

### 모바일 UI·검색 상태·오류·알림

- M `mobile/package.json`
- M `mobile/src/api/client.ts`
- M `mobile/src/api/recommendations.ts`
- M `mobile/src/api/request-retry.ts`
- M `mobile/src/app/(tabs)/_layout.tsx`
- M `mobile/src/app/(tabs)/explore.tsx`
- M `mobile/src/app/(tabs)/index.tsx`
- M `mobile/src/app/(tabs)/mypage/index.tsx`
- M `mobile/src/app/(tabs)/mypage/reports.tsx`
- M `mobile/src/app/(tabs)/mypage/saved-places.tsx`
- M `mobile/src/app/(tabs)/recommend.tsx`
- M `mobile/src/app/_layout.tsx`
- M `mobile/src/app/login.tsx`
- M `mobile/src/app/notifications.tsx`
- M `mobile/src/app/place-report.tsx`
- M `mobile/src/app/signup.tsx`
- M `mobile/src/auth/auth-context.tsx`
- M `mobile/src/components/place-detail-sheet.tsx`
- M `mobile/src/components/place-map.tsx`
- M `mobile/src/components/place-map.web.tsx`
- M `mobile/src/components/place-photo.tsx`
- M `mobile/src/components/report-detail.tsx`
- M `mobile/src/components/screen.tsx`
- M `mobile/src/hooks/use-action.ts`
- M `mobile/src/hooks/use-resource.ts`
- M `mobile/src/utils/place-identity.ts`
- U `mobile/src/hooks/use-notifications.ts`
- U `mobile/src/utils/back-navigation.ts`

### 문서 — 작업별 선택

- U `docs/NAVER_PLACE_EVIDENCE_SEARCH_COMPARISON.md`
- U `docs/SEARCH_CONVERSATION_QUALITY_REPORT.md`
- U `docs/SEARCH_EVIDENCE_PIPELINE_COMPLETION_2026-10-06.md`
- U `docs/SEARCH_EVIDENCE_VALUE_DIAGNOSIS_2026-10-06.md`
- U `docs/SEARCH_UX_COMPLETION_REPORT.md`

### 디자인 산출물 — 기본 제외

- U `docs/ui-concepts/app-icon-draft-01.png`
- U `docs/ui-concepts/app-icon-draft-02.png`
- U `docs/ui-concepts/app-icon-draft-03-cards.png`
- U `docs/ui-concepts/app-icon-draft-05-selection.png`
- U `docs/ui-concepts/app-icon-draft-06-recommendation.png`

### 웹·모바일 공통 계약

- U `shared/search-ux.ts`
- U `shared/user-message.ts`

### runtime·산출물 제외

검사 시 runtime의 비무시 untracked 파일은 7,492개였다. APK·DB·로그/JSON·이미지·의존성/캐시·인증서 등을 포함한다. runtime 전체, 격리 검사 helper·objects·index, 아이콘 초안 5개는 기본 제외한다. 인증서 확장자 자체를 비밀키 증거로 해석하지 않으며 내용을 출력하지 않았다. `.env*`, 비밀값, 개인정보, 원문 로그, 빌드 산출물을 자동 추가하지 않는다. 삭제·새 ignore 정책 변경도 이번 범위에서 수행하지 않는다.

## 파일 안에 섞인 작업과 독립 커밋 후보

| 후보 | 범위·동반 검사 | 의존성·분리 기준 |
|---|---|---|
| C1 대화 의미·엄격 조건 | conversation_patches/sessions, ai_intent_planner, hard_gate 및 대화/fallback/quality tests | ai_search_orchestrator의 required-condition/fallback·previous-result hunk만 함께. views의 turn version/409 hunk 동반 |
| C2 근거 후보·외부 identity·진단 | external_place_identity, candidate_trace, pipeline_metrics, ai_web_search_provider, tag_evidence_aggregation, 진단 command 및 관련 tests | C1 뒤; orchestrator의 raw Evidence retrieval/identity/web policy/trace hunk. views의 후보 trace·검색 metrics hunk 포함 |
| C3 수집 결핍 우선순위 | bootstrap_priority, search_coverage_demand 및 관련 test | C2 뒤 권장. collection 최신 bounded planner와 정책 의미 확인 |
| C4 공통 메시지·공개 제보 | shared/user-message, serializer 및 제보 views hunk, mobile_admin_workflows, 사용자 제보 화면·공통 오류 hook | serializer와 views를 C1/C2에서 파일 통째로 가져오지 않음. 내부 정보 비노출·타인 상세 404 검사 동반 |
| C5 웹·앱 검색 UX | shared/search-ux, history/back/panel, 웹 Home/Map/useHomeSearch, 앱 recommend/explore/index, 지도·사진 및 관련 UI tests | C1 및 C4 계약 이후; 기존 release Android UX와 충돌 먼저 해결. generation/state-version/clarification 보존 hunk와 화면 hunk를 원자적으로 검토 |
| C6 알림·계정 상태 | 웹/앱 notification hook·화면 및 notifications tests | C4 뒤; 계정 전환·늦은 응답 차단 동반 |
| C7 공통 모듈 빌드·검사 | gateway Dockerfile의 shared COPY, vite 확장자, mobile package/test config | C4/C5에 필요한 것은 해당 커밋에 동반. test:ux와 현재 CI 실행 명령 차이를 해소한 뒤 별도 CI 후보 |
| D 문서 | 작업별 completion 보고서 + 이 계획 + 공통 state의 필요한 부분 | 각 코드 후보에 정확한 tree/SHA·검사 범위를 붙인 뒤 선택 |

실제 hunk 확인: orchestrator에 raw Evidence 추가·identity 병합·필수조건 정책·Web Search 파일럿·metrics가 동시에 존재한다. views에 공개 제보 serializer 교체(약 504~598행), 지도 trace/metrics(약 1462~1804행), AI trace/대화 turn version(약 3178~3296행)이 섞여 있다(행은 원본 diff 기준). useHomeSearch와 mobile recommend에는 서버 상태/늦은 응답 처리와 화면·뒤로가기 작업이 함께 있다. HomeView·MapSearchView 및 관련 tests도 두 작업 문서에 걸치므로 파일 단위 담당 추정은 불충분하다.

후보는 아직 새 커밋이 아니다. 소유자 확정·hunk 분리와 최신 기준 재적용이 끝나야 개별 적용/되돌리기 가능한 커밋이 된다. 공유 checkout에서 `add -A`, commit, push, checkout, reset/clean/stash를 수행하지 않는다. runtime의 별도 index와 object store에만 공유 변경을 snapshot했고 이는 충돌 검사 전용이다. 임의로 작성자 변경하거나 다른 채팅 변경을 자신의 커밋으로 기록하지 않는다.

## 실제 격리 충돌 검사

Git 2.55의 merge-tree로 별도 object store를 사용했다. 공용 index hash는 검사 전후 동일했다. ref를 만들거나 checkout을 바꾸지 않았다.

| 검사 | 결과 |
|---|---|
| 현재 HEAD + release-foundation | exit 0, 충돌 0 |
| 현재 HEAD + service-flow-verification | exit 0, 충돌 0 |
| collection + service-flow-verification | exit 0, 충돌 0; 이미 포함 |
| collection + release-infra | exit 0, 충돌 0 |
| collection → service-flow → infra 순서 | exit 0, 충돌 0 |
| 위 baseline + 공유 미커밋 code/tests/shared snapshot | exit 1, 아래 8개 충돌 |

- `frontend/src/views/MapSearchView.jsx`
- `frontend/src/views/home/PlaceResultList.jsx`
- `mobile/src/app/(tabs)/explore.tsx`
- `mobile/src/app/(tabs)/index.tsx`
- `mobile/src/app/(tabs)/mypage/reports.tsx`
- `mobile/src/app/(tabs)/recommend.tsx`
- `mobile/src/app/login.tsx`
- `mobile/vitest.ux.config.mjs`

8개 중 vitest config는 add/add로 release 브랜치에 이미 있는 검사 구성이 공유 untracked 구성과 겹친다. 나머지 7개는 화면/상태 변경이 겹친다. 최신 release의 사진 업로드·저장 출처·로그인/가입·안드로이드 UX를 기준으로 보존하고, 미커밋 서버 canonical 조건·늦은 응답 방지·history/panel/message 변경을 의미별로 재적용해야 한다. 충돌 marker를 일괄 ours/theirs로 해결하지 않는다. 기능 코드 수정은 요청 범위 밖이므로 이번에 해결하지 않았다.

이 검사는 문서·runtime·디자인을 제외한 snapshot 대상이다. 자동 병합 성공 파일에도 의미 충돌이 있을 수 있다. 충돌 없는 기존 통합 tree는 `0857895db205e713ddbb0e14dc6a36a000b47d58`; 충돌 결과 tree는 승인/배포용이 아니다. `git diff --check`는 exit 0. 현재 79개 변경의 기능 tests를 이번 문서 작업에서 재실행하지 않았다.

## CI·기존 증거와 통합 영향

GitHub Actions 실행 [36537940292](https://github.com/binkim00/life-infra-map/actions/runs/36537940292)의 최신 attempt 네 job(Django/Spring/웹/앱 코드)이 success인 것을 connector로 재조회했다. 기존 CODEX_STATE가 이 run을 `c734d66e7e6ae790384c777e186081a067e14d9d` push와 연결한다. job API는 head_sha를 반환하지 않아 run↔SHA 연결은 기존 기록임을 구분한다. 해당 SHA의 workflow 범위는 Django accounts/boards/recommendations, Spring test, 웹 test/build, 앱 tsc/lint/node tests다. 이 증거를 최신 미커밋 snapshot·통합 tree의 통과로 확대하지 않는다.

10월 6일 보고서의 Django 1,004/19 skip, 웹 113~114, 앱 UX 9/연결 6 및 TypeScript/lint는 과거 공유 dirty tree 결과이고 고정 commit/tree 증거가 없다. 범위 참고만 재사용한다. 출시/수집의 과거 배포·실기기 성공도 해당 SHA·기기·날짜의 증거이며 현재 통합 완료를 뜻하지 않는다.

master에는 workflow가 없고 검사한 후속 6개 ref에는 `.github/workflows/ci.yml` 하나만 있다. 원격 tip이 로컬 refs와 일치해 해당 고정 tree의 workflow를 검사했다. push/PR/workflow_dispatch로 네 구성요소 검사를 실행하며 서버 접속·배포·migration·스토어 업로드 단계가 없다. **현재 추적 workflow 기준 master 병합으로 자동 운영 배포되지 않는다.** GitHub UI의 외부 webhook/별도 서비스 연계는 이번에 전수 확인하지 않았으므로 그것까지 없다고 단정하지 않는다.

현재 mobile `test:ux`는 frontend의 Vitest·의존성을 재사용하지만 CI mobile job은 mobile npm ci + npm test만 실행한다. job별 파일시스템이 달라 frontend job 설치를 빌려 쓸 수 없다. 새 UX 검사를 CI에 넣는 후보는 frontend 의존성 설치와 test:ux 실행을 함께 검토해야 한다. 원본 CI가 UX 테스트를 검증한다고 보고하지 않는다.

기존 master 대비 통합은 검색/대화·계정 삭제·공개 제보·프록시 신뢰 경계·모바일 인증/사진/저장·수집 pacing·배포 도구를 포함하는 큰 변화다. 코드 병합과 migration 실행, 서버 이미지 교체, 데이터 변경은 각각 다른 승인·검증 대상이다.

master 이후 migration 추가 경로를 이력에서 확인했다. `758e1df0`에 accounts 0005_refreshsession/0006_socialidentity/0007_socialloginticket, boards 0010_inquiry_category, recommendations 0029_place_icontains_search_indexes/0030_place_compact_search_indexes/0031_place_name_prefix_index가 있다. `31bae5f7`에 boards 0011_allow_resolved_report_deleted_target, `8342a596`에 recommendations 0032_collectionplannerstate_and_more가 있다. 이번에 schema나 migration을 수정·실행하지 않았다. 운영 적용 여부는 이번 Git 조사로 확정하지 않으며 이후 배포 요청에서 실제 적용 이력과 잠금/인덱스 영향을 확인해야 한다.

## 업로드 → PR → master 순서와 승인 지점

| 단계 | 구체 대상 | 승인·검증 |
|---|---|---|
| 1 기존 출시 기반 PR | `codex/release-foundation@5550de65 → master@ff456069` | 이미 원격에 존재. 69개 기존 커밋·변경 목록·공개 자료 검토 후 PR 생성 승인, 정확한 head/base의 CI 확인 후 merge 별도 승인 |
| 2 수집 개선 PR | `codex/collection-resource-budget@76e2de2f → master` | 단계 1 merge 후 추가 원본 5개만 리뷰. bounded planner·provider budget·quota recovery 관련 검사, merge 승인 |
| 3 수동 배포 도구 업로드/PR | `codex/release-infra@c33eb397 → master` | 업로드 전 remote 동명 ref 재조회·부재/기대 old SHA 확정, 유일 commit 3파일 review·업로드 승인. 단계 1/2 후 diff는 도구 3파일, 로컬 prepare/apply/rollback 회귀 확인 후 PR/merge 승인 |
| 4 미커밋 기능 후보 | 새 `codex/integration-search-*`/UX 등, 최신 승인 master 기반 독립 작업 공간 | 먼저 8개 충돌 해결·소유자/hunk 확인, 제외 목록·commit/tree 확정·관련 tests. 그 후 정확한 파일·SHA·원격 ref를 제시해 commit/push/PR 승인 |
| 5 실제 잔디 확인 | 원본 SHA의 master 도달 여부 + 작성자 GitHub 연결 | 병합 후 직접 조회. 그 다음 별도 배포 요청이 있을 때만 운영 작업 |

각 merge는 **merge commit 방식**을 권장한다. 원본 SHA와 작성 이력을 유지하므로 후속 branch 비교도 원본 ancestry를 그대로 쓸 수 있다. 단계 1 이전 collection→release의 5개 diff를 별도 리뷰할 수 있으나 master 승격은 위 순서다. service-flow와 disk의 중복 PR/업로드는 만들 필요가 없다. 현재 HEAD 9개만 별도 push해도 잔디의 기본 브랜치 조건은 해결되지 않는다. stage 3 branch에는 공통 46개가 있으므로 stage 1 후 대상 diff가 고유 1개인지 다시 확인한다. 원격 master 변경 시 본 검사를 새로운 head/base로 재수행한다.

GitHub 공식 기준상 commit은 연결된 이메일·독립 저장소·default/gh-pages branch 등 조건을 충족해야 profile graph에 집계된다. 기존 대표 commit의 작성자가 binkim00에 연결됨은 이번 원격 commit 응답에서도 확인했지만 모든 과거 author 이메일을 전수 검사하지 않았다. 미커밋은 commit으로 기록되지 않고, branch push만으로 기본 브랜치 도달 조건을 충족하지 않는다. 합병 후 원래 author date 기준 과거 날짜에 반영되므로 오늘 날짜로 이력을 옮기지 않는다. [기여 조건·날짜](https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference)

Squash는 기본 브랜치에 새 한 커밋으로 압축해 원본 개별 SHA/날짜의 도달성을 남기지 않으므로 과거 개별 commit 잔디 복원을 목표로 할 때 부적합하다. Rebase merge는 개별 commit을 남기지만 GitHub가 committer와 SHA를 다시 만들어 과거 검증 SHA·ancestry 비교가 달라진다. 원본 작성자의 기여 조건은 여전히 적용된다. 이번 계획은 이력 보존이 우선이므로 불필요한 squash/rebase·force push·author/date 조작을 하지 않는다. [병합 방식](https://docs.github.com/en/pull-requests/reference/pull-request-merges)

## 남은 일과 다음 행동

완료: 원격 tip 재확인, 중복 없는 ancestry·patch 조사, 9개 commit 경로/제한적 민감 산출물 검토, 미커밋 파일·혼합 hunk 분류, 격리 충돌 검사, CI/배포 workflow 범위 확인, 단계별 승인안 작성. 남은 일: 승인된 기존 이력 PR 작업, 미커밋 소유자·hunk 분리와 8개 충돌 해결, 새 tree 관련 검사, 최종 merge 후 profile 반영 직접 확인. 운영·스토어 실행은 이 계획에서 하지 않는다.

### 09:18 KST 후속 — 승인된 draft PR 생성 완료

사용자가 출시 기반 69개 커밋의 draft PR 생성을 승인했다. 생성 직전 원격 비교 69 ahead/0 behind·228개 변경 파일과 head/base SHA를 재확인하고 동일 대상의 열린 PR이 없음을 확인했다. [Draft PR #3](https://github.com/binkim00/life-infra-map/pull/3)을 생성해 이 채팅에 연결했다. 재조회 결과 open/draft/merged=false, mergeable=true, base `ff4560695b134b4ed8c1ce17047d8526c97d4ae2`, head `5550de6532ae014ec6cbf923ebc0659097e1a2c2`, 69 commits/228 changed files다. PR 응답의 merge_commit_sha는 미병합 상태의 GitHub 테스트 병합 SHA이므로 실제 master 병합으로 해석하지 않는다.

PR CI [38326570685](https://github.com/binkim00/life-infra-map/actions/runs/38326570685)는 첫 조회에서 queued/conclusion=null이었다. 성공으로 보고하지 않으며 지속 polling하지 않았다. 로컬 add/commit/push, 원격 병합, 운영·DB·스토어 작업은 수행하지 않았다.

### 09:24 KST 후속 — PR CI·격리 모바일 UX 검사 완료

사용자의 단계적 자체 진행 요청에 따라 CI 완료 결과를 확인했다. run `38326570685`는 completed/success이며 Django·Spring·웹·앱 코드 네 job의 실행 단계 모두 success다. Code Review checks API의 headRevision과 각 check head_sha가 `5550de6532ae014ec6cbf923ebc0659097e1a2c2`에 일치해 과거 c734d66e의 CI로 대체하지 않았다. 네 annotation은 ubuntu-latest 실행 이미지 변경 notice이고 실패가 아니다. PR은 draft/open/merged=false·mergeable=true로 유지했다.

모바일 UX는 현재 CI job 밖이므로 고정 head의 mobile/shared를 runtime 별도 공간에 추출해 두 suite/9개 테스트 통과를 추가 확인했다. 제품 소스와 기존 test 내용은 그대로다. 원본 명령은 격리 의존성/tsconfig 경로와 Windows sandbox 임시파일 rename 제약으로 시작 실패했다. 최종 검사는 기존 의존성을 재사용하고 Expo tsconfig를 절대경로로 연결했으며 이미 기존 test에서 mock하는 native/router/storage 모듈을 격리 alias로 연결한 harness에서 통과했다. 따라서 고정 코드의 모의 UX 검사 성공이며 원본 npm 명령의 완전한 재현·클린 dependency 설치·실기기 검증은 아니다. runtime helper·의존성 연결·harness·캐시는 Git 추가 대상에서 제외한다.

검토 범위는 Git 통합·CI·migration 경로·계정 삭제/프록시 변경 표적 확인이다. 228개 파일의 전수 기능/보안 리뷰로 표현하지 않는다. gateway Dockerfile에는 shared COPY가 없지만 이 고정 head의 frontend에는 shared import도 없어 현재 PR의 빌드 결함으로 판단하지 않았다. 이후 미커밋 웹 UX가 shared를 가져오는 시점에는 기존 계획 C7의 COPY와 Vite 확장자 처리가 필요하다. Docker daemon이 없어 실제 gateway 컨테이너 build는 이번에 실행하지 않았다. 추적 diff whitespace 검사 통과, 공유 HEAD `6f1f8323`·staged 0을 유지했다. 최신 검증과 한계를 PR 본문에 갱신했다.

현재 병합 실패나 CI 실패는 확인되지 않았다. 다음 master 변경은 앞서 정한 별도 병합 승인 경계다. 승인 후 merge commit으로 PR #3을 병합하고 원격 master의 원본 head 도달성을 확인한 다음 수집 5개 단계로 넘어가야 한다. 병합 전 수집 PR을 master에 열면 출시 69개가 다시 포함되므로 지금 중복 PR을 만들지 않았다.

### 09:28 KST 후속 — 승인된 PR #3 master 병합 완료

사용자가 조건부 병합을 승인했고 직전 head/base·mergeable·네 CI check success가 기존 승인 범위와 같음을 확인했다. draft를 ready로 전환한 뒤 expected_head_sha `5550de6532ae014ec6cbf923ebc0659097e1a2c2`를 지정해 merge commit 방식으로 병합했다. 반환 merged=true, merge SHA는 `431cde2a481ff05c11780cd65b46b7d20c8a7fae`다. 재조회에서 PR closed/merged=true, merged_at 2026-10-13 09:28:16 KST와 원격 master tip의 같은 SHA를 확인했다.

원격 compare `5550de65 → master`는 앞선 원본 head가 공통 조상, ahead 1/behind 0, 변경 파일 0개로 확인됐다. 원본 69개 커밋은 SHA를 유지한 채 기본 브랜치에 포함됐다. 잔디의 기본 브랜치 도달 조건은 해결됐지만 실제 profile graph 재집계/화면 반영은 별도로 확인하지 않았으므로 잔디 표시 완료로 표현하지 않는다.

후속 collection을 새 master와 읽기 전용 비교하면 head 고유 5개·base 고유 merge commit 1개, 변경 파일 12개다. 이는 master 병합 커밋에서 생긴 정상 분기이며 출시 69개가 다시 미통합된 것이 아니다. 로컬 remote-tracking master는 fetch하지 않아 여전히 과거 snapshot일 수 있으며 이번 원격 확인과 구분한다. 현재 checkout·공용 index·운영 서비스/설정/데이터·스토어는 변경하지 않았다. post-merge push CI의 결과는 이번 병합 검증으로 대체하지 않는다.

### 09:32 KST 후속 — 수집 5개 커밋 검토·draft PR #4 준비 완료

사용자의 수집 후속 검토/PR 준비 요청으로 원격 새 master `431cde2a481ff05c11780cd65b46b7d20c8a7fae`와 head `76e2de2f9b30ad096022197dd946138d2a52668f`를 비교했다. 후속 원본은 `8342a596`, `2a600bf9`, `0a7198dc`, `28b8b51d`, `76e2de2f` 다섯 개이며 변경은 아래 12파일이다.

- `backend/config/collection_pg_test_settings.py`
- `backend/config/settings.py`
- `backend/recommendations/management/commands/plan_daily_tag_collection.py`
- `backend/recommendations/management/commands/process_place_tag_collection_jobs.py`
- `backend/recommendations/management/commands/recover_tag_collection_jobs.py`
- `backend/recommendations/management/commands/run_tag_collection_scheduler.py`
- `backend/recommendations/migrations/0032_collectionplannerstate_and_more.py`
- `backend/recommendations/models.py`
- `backend/recommendations/services/bounded_collection_planner.py`
- `backend/recommendations/services/collection_resources.py`
- `backend/recommendations/test_collection_resources.py`
- `docs/operations/collection-resource-budget.md`

검토: 기본키 페이지·refill/queue 제한, sparse JSON의 LIMIT 선적용, 기존 품질 bucket 예산·커서 진행, provider별 claim/낮은 quota 상한, 예약 날짜·한 번만 정산·checkpoint 재개·소유권 fencing과 heartbeat를 확인했다. SQL/lock timeout은 트랜잭션 범위이며 wall deadline은 SQL 경계에서 검사하므로 정확한 CPU 상한은 아니다. migration은 0031 의존의 신규 0032로 planner state 테이블 하나·nullable job 필드 셋을 추가한다. 기존 migration/큐를 삭제·reset하지 않는다. 두 기능 플래그는 기본 false지만 worker/recovery ORM은 새 필드를 사용하므로 코드 배포 전 0032 적용 확인이 필요하다. 스위치 off만으로 schema 요구가 제거되지는 않는다.

고정 head backend만 `runtime/collection-fixed-head-review`에 추출했다. LFS fixture는 pointer 상태이며 이번 합성 fixture 테스트는 이를 사용하지 않는다. Python 3.12.12/Django 6.0.5와 기존 `runtime/test-deps`로 관련 6모듈 87개 검사 중 **80개 통과·PostgreSQL 전용 7개 제외**, 5.370초. system check 정상, 모델 migration 생성 검사 No changes detected, 변경 Python AST·git diff check 통과. 고신뢰 private-key/AWS-key/GitHub-token 패턴 0이며 완전한 비밀/개인정보 감사는 아니다. 현재 SQLite 결과는 실제 PostgreSQL 잠금/heartbeat/SQL timeout·0032 큐 보존·EXPLAIN 검증을 대신하지 않는다. 과거 branch 문서의 PostgreSQL 86개 성공은 그 시점 환경의 기록이고 최종 sparse-history 검사가 추가된 이번 87개와 구분했다.

현재 검토와 관련 회귀에서 PR 준비 차단 문제는 발견되지 않았다. [Draft PR #4](https://github.com/binkim00/life-infra-map/pull/4)를 생성·이 채팅에 연결하고 고정 SHA·5개/12파일·검증·migration 선행조건·제외 범위를 명시했다. 수집 근거 품질과 목표 처리량은 별도 과제이며 자원 제한의 성능 효과로 확대하지 않는다. 운영의 동일 SHA 배포/CPU 상태는 공통 문서의 과거 직접 조회 기록으로만 인용했다. 이번 작업에서 운영 재조회/설정/데이터/migration 실행/배포/원격 병합은 하지 않았다. 공유 HEAD·공용 index와 다른 채팅의 변경을 보존했다.

PR 재조회: open/draft/merged=false·mergeable=true, base/head SHA 유지, 5 commits/12 changed files. CI [38327724839](https://github.com/binkim00/life-infra-map/actions/runs/38327724839)는 최초 조회 in_progress/conclusion=null이다. 진행 중 상태를 성공으로 표현하지 않았고 지속 polling하지 않았다.

### 09:34 KST 후속 — 승인된 PR #4 master 병합 완료

사용자가 PR #4 CI 확인 후 원본 이력 유지 병합을 승인했다. run `38327724839` completed/success, Django/Spring/웹/앱 코드 네 job의 모든 실행 단계 success 및 각 check head_sha `76e2de2f9b30ad096022197dd946138d2a52668f`를 확인했다. 네 annotation은 ubuntu-latest 실행 이미지 변경 notice이고 실패가 아니다. 승인된 base `431cde2a`와 head, mergeable=true·5커밋/12파일이 유지됨을 확인해 PR 본문에 최종 검증을 기록했다.

Draft를 ready로 전환하고 expected_head_sha를 지정해 merge commit 방식으로 병합했다. 결과 merged=true, merge SHA `b9ec93ed24478930d5d64d00991c2c25558adf8a`. 재조회 PR closed/merged=true, merged_at 2026-10-13 09:34:55 KST와 원격 master의 같은 tip을 확인했다. 원격 `76e2de2f → master` 비교는 해당 head가 공통 조상, ahead 2/behind 0(두 PR merge commit), 파일 차이 0이다. 따라서 원본 후속 5개 SHA가 master에서 보존됐다. 원본 74개 커밋은 이제 기본 브랜치에 포함되며 release-infra 고유 c33eb397과 공유 미커밋 변경은 별도 잔여 범위다.

로컬 checkout/index·운영 서비스/설정/데이터·migration 실행·배포·스토어 변경은 없다. post-merge push CI나 실제 profile graph 표시 완료는 아직 확인하지 않았으며 PR CI/원격 반영과 구분한다.

### 09:40 KST 후속 — 수동 배포/복구 도구 검토·업로드·draft PR #5 완료

사용자가 도구 1개 커밋·3파일의 검토 후 업로드/draft PR 생성을 승인하고 실제 운영 배포를 제외했다. 원본 `c33eb397d0ce81faf8b3308f0b1d3d2b1837aa57`의 README·prepare_release.py·apply_release.py를 읽어 고정 Git blob 선별 패키징, manifest 일치/중복/size/hash, 금지 경로와 symlink 검사, 읽기 전용 preview, 앱 밖 새 backup, 파일별 원자 교체, 예외 복원·변경/백업 hash를 확인하는 rollback을 검토했다.

원본 도구를 runtime 별도 공간에 추출하고 합성 파일만 사용하는 **13개 회귀 중 12개 통과·symlink 생성 불가 1개 제외**, 1.896초. preview 무변경, apply/rollback, payload 변조/추가/중복 거부, 금지 경로·앱 내부/기존 backup 거부, 이후 수정·백업 변조 시 복구 거부, 중간 교체 예외 복원, 고정 commit 패키징·기존 ZIP 덮어쓰기 거부를 확인했다. Windows 제한 환경의 경로 확인 오류는 workspace/runtime에만 쓰는 동일 검사를 허용 환경에서 실행해 해소했다. 제품 소스는 수정하지 않았다. AST·diff check 통과, 제한적 고신뢰 key/token 패턴 0.

사용 조건: Linux 서버 대상이며 실제 Linux symlink 검사는 이번에 하지 않았다. CI-run 값은 기록용·성공 자동 확인이 아니고 manifest hash는 서명/진본 인증이 아니다. 신뢰된 전송·외부 ZIP/도구 hash 확인이 선행한다. 파일별 원자 교체·처리된 Python 예외 복원이고 전체 배포의 트랜잭션/강제 종료/전원 장애 자동 복구 보장은 아니다. 삭제/migration/환경변수/권한 변경 중단 규칙은 운영자가 확인해야 한다. 신규 shared 모듈 등 허용 경로 밖 파일이 필요한 배포는 이 도구 범위/허용 목록을 별도로 검토한다.

원격 동일 브랜치 없음은 허용된 네트워크의 ls-remote로 확인했다. 별도 bare 저장소 `runtime/release-infra-upload-20261013.git`가 공유 objects를 읽기만 하게 구성해 `c33eb397:refs/heads/codex/release-infra`를 업로드했다. empty expected-ref lease로 다른 주체가 먼저 생성하면 덮어쓰지 않게 했으며 기존 이력의 force rewrite는 하지 않았다. 원격 commit SHA 일치와 새 master 대비 **고유 1개/새 파일 3개**를 직접 확인했다. 뒤처진 30개는 기존 분기점 이후 master 이력이며 PR 삭제/되돌리기 대상이 아니다.

[Draft PR #5](https://github.com/binkim00/life-infra-map/pull/5)를 생성·연결했다. base `b9ec93ed24478930d5d64d00991c2c25558adf8a`, head 원본 `c33eb397...`, open/draft/merged=false, 1 commit/3 files다. CI 최초 조회: run 38328447025: in_progress/결과 없음. 이 CI는 위 도구 로컬 회귀를 자동 실행하지 않으므로 두 증거를 구분한다. 실제 운영 접속/배포·서비스/설정/공유 데이터/migration·스토어 변경은 없다. 공유 index·현재 HEAD `6f1f8323`·기존 tracked/untracked 작업은 보존했다.

### 09:44 KST 후속 — PR #5 고정 head/base CI 병합 검토 기록 완료

사용자의 결과 확인/기록 요청으로 PR #5와 CI run `38328447025`를 재조회했다. head `c33eb397d0ce81faf8b3308f0b1d3d2b1837aa57`, base `b9ec93ed24478930d5d64d00991c2c25558adf8a`, 1 commit/3 files가 유지됐다. PR은 open/draft/merged=false·mergeable=true다. run completed/success, Code Review checks의 headRevision과 각 check head_sha가 고정 head에 일치하며 네 job의 모든 실행 단계가 success다.

| Job / ID | 직접 확인한 실행 범위 | 결과 |
|---|---|---|
| Django / 115072474926 | Python 3.12, requirements 설치, accounts/boards/recommendations 테스트, config.test_settings | success |
| Spring / 115072474987 | Java 21, Gradle test --no-daemon | success |
| 웹 / 115072474843 | Node 24, npm ci, npm test, production build | success |
| 앱 코드 / 115072475006 | Node 24, npm ci, TypeScript 검사, lint, Node tests | success |

각 job의 annotation을 개별 확인했다. 네 항목 모두 ubuntu-latest 실행 이미지 변경 notice이며 경고/실패 테스트가 아니다. 상세 검사 결과는 [CI run](https://github.com/binkim00/life-infra-map/actions/runs/38328447025)과 PR 본문에 기록했다. PR 응답의 테스트 merge SHA `0b3446d689b4d242d5857f78c199568b28af4d0d`는 미병합 상태의 GitHub 테스트 병합 값이며 실제 master 반영이 아니다.

이 CI는 배포 도구 자체의 apply/rollback 회귀, 모바일 test:ux, Android/iOS native build, 실제 PostgreSQL·운영 적용/복구를 실행하지 않는다. 도구 12통과/Windows symlink 1제외는 직전 별도 로컬 회귀 증거로 유지했고 새 CI의 자동 실행 결과로 확대하지 않았다. 테스트 개수·운영 성공·실기기 성공은 job step 성공으로 추정하지 않았다. 현재 확인한 CI와 충돌 상태에는 병합 차단 문제가 없으며 사용 조건/운영 검증 한계는 그대로다.

이번 요청은 CI 결과 기록까지이며 draft 전환·병합·배포·공용 index/checkout 변경은 하지 않았다. PR 본문 및 공통 상태의 해당 항목만 갱신했다.

### 09:46 KST 후속 — 승인된 PR #5 master 병합·반영 확인 완료

사용자가 원본 이력 유지 병합과 master 반영 확인을 승인하고 실제 운영 배포를 제외했다. 직전 조회에서 고정 head `c33eb397d0ce81faf8b3308f0b1d3d2b1837aa57`/base `b9ec93ed24478930d5d64d00991c2c25558adf8a`, 1 commit/3 files, mergeable=true 및 run `38328447025`의 동일 head 네 check success를 재확인했다. draft를 ready로 전환한 뒤 expected_head_sha를 지정해 merge commit 방식으로 병합했다.

GitHub 반환 merged=true, merge SHA `84e3ebf780d4cb53041c8721b929c5a52bd0fccd`. 재조회 PR closed/merged=true·merged_at 2026-10-13 09:46:59 KST와 원격 master의 같은 tip을 확인했다. `c33eb397 → master`의 merge-base가 원본 c33eb397, behind 0이므로 원본 commit은 master 조상으로 보존됐다. 이 비교의 ahead 31개는 이전 출시/수집/merge 이력으로 정상이다. 병합 직전 master `b9ec93ed → master`는 ahead 2/behind 0이며 변경 파일이 deploy/release의 README·apply_release.py·prepare_release.py 세 신규 파일뿐임을 확인했다. 소스 파일별 내용은 각각 108/198/110행 추가로 기존 검토 범위와 일치한다.

따라서 이번 기존 브랜치 통합 대상의 고유 원본 75개(출시69+수집5+도구1)는 PR #3/#4/#5의 merge commit으로 기본 브랜치에 포함됐다. 공유 미커밋 변경과 최신 별도 작업은 아직 독립 분리/검토 대상이다. 현재 checkout/index 유지, 실제 운영 배포·서비스/설정/공유 데이터·migration·스토어 변경은 없다. post-merge push CI와 실제 profile 잔디 화면은 이번 원격 반영 확인으로 대체하지 않는다.

**다음 한 가지 행동:** 새 master `84e3ebf7` 기준 최신 공유 미커밋 변경을 비교해 이미 포함된 변경과 잔여 독립 커밋 후보·충돌 목록을 다시 분류한다.


### 최신 미커밋 재분류 — master 84e3ebf7 기준

원격 master를 runtime의 별도 bare 저장소에 받아 정확한 tip `84e3ebf780d4cb53041c8721b929c5a52bd0fccd`를 확인했다. 공유 HEAD `6f1f8323cc87e3def055905a69e44c3af8322221`는 이전 기준이므로 HEAD 상대 diff를 새 미반영 변경 수로 해석하지 않는다. 공용 index 대신 별도 index/objects에 코드 snapshot을 만들고 master와 blob·3-way 비교했다. CRLF/LF는 Git clean 변환 기준이다. 합성 commit은 충돌 검사 전용 object이며 branch/실제 커밋·업로드가 아니다.

| 구분 | 파일 수 | 판단 |
|---|---:|---|
| 현재 HEAD 대비 tracked 변경 | 102 | master 포함분과 잔여가 혼합 |
| runtime 제외 untracked 파일 | 68 | 코드45 + 문서18 + 디자인5 |
| 코드·설정·검사 총계 | 147 | tracked102 + untracked45 |
| master과 내용이 동일 | 62 | 독립 커밋 대상에서 제외, 로컬 삭제/되돌리기는 하지 않음 |
| master 기존 파일의 잔여 차이 | 64 | master 대비 hunk 선별 필요 |
| master에 없는 신규 코드·검사 | 21 | 관련 기능과 함께 후보 구성 |
| 문서 | 18 | 해당 후보의 증거/검증 문서로 동반 |
| 디자인 초안 | 5 | 기본 제외 |
| runtime 산출물 | 9,862 | 기본 제외, 전체 add 금지 |

총 잔여85개는 64+21이며 완성된85파일 커밋을 뜻하지 않는다. 스냅샷 중 코드 hash 변경0, 공용 index hash·HEAD 유지, tracked diff whitespace 검사 통과다. 한글 runtime 경로23개의 Git 인용 출력을 정정해 제외했으며 실제 삭제 파일은0이다.

**최신 충돌12개:** 오래된 HEAD + 공유 dirty snapshot을 master와 merge-tree한 결과이며 공용 소스에는 충돌 마커를 쓰지 않았다. 이전8개 중 index/login/vitest 설정 충돌3개가 사라지고 backend4개·README/account-deletion/conversation3개가 추가되어 총12개다. 이미 통합된 후보도 과거 HEAD가 공통 부모라 충돌할 수 있으므로 12개를12개 기능 결함으로 해석하지 않는다.

- `backend/config/settings.py`
- `backend/recommendations/management/commands/process_place_tag_collection_jobs.py`
- `backend/recommendations/management/commands/run_tag_collection_scheduler.py`
- `backend/recommendations/services/bounded_collection_planner.py`
- `frontend/src/views/MapSearchView.jsx`
- `frontend/src/views/home/PlaceResultList.jsx`
- `mobile/README.md`
- `mobile/src/app/(tabs)/explore.tsx`
- `mobile/src/app/(tabs)/mypage/reports.tsx`
- `mobile/src/app/(tabs)/recommend.tsx`
- `mobile/src/app/account-deletion.tsx`
- `mobile/tests/ux/conversation.test.jsx`

**독립 커밋 후보 재분류:** 파일 목록은 주분류이며 혼합 파일의 hunk 의존성은 아래 조건이 우선한다. 아직 어떤 후보도 새 master 기준 완성 tree·관련 검사를 마친 커밋으로 확정하지 않았다.

#### T1 수집 P0 계측 — 9파일

master의 CPU 제한·0032·예약/정산/heartbeat 기반 위에 계측 hunk만 분리. worker/planner/scheduler 충돌 3개; recovery/models/collection_resources/0032는 이미 master이므로 재추가 제외. 과거 composite patch 재적용 금지. 가장 먼저 격리 후보 구성 권장.

- `backend/recommendations/management/commands/plan_daily_tag_collection.py`
- `backend/recommendations/management/commands/process_place_tag_collection_jobs.py`
- `backend/recommendations/management/commands/report_daily_collection.py`
- `backend/recommendations/management/commands/run_tag_collection_scheduler.py`
- `backend/recommendations/management/commands/summarize_collection_metrics.py`
- `backend/recommendations/services/bounded_collection_planner.py`
- `backend/recommendations/services/collection_telemetry.py`
- `backend/recommendations/test_bounded_collection_telemetry.py`
- `backend/recommendations/test_collection_telemetry.py`

#### C1 대화 의미·엄격 조건 — 10파일

orchestrator는 C2와 혼합, views/tests.py는 C4 주분류이나 대화 version/409 hunk는 C1 동반. 파일 통째 커밋 금지.

- `backend/recommendations/services/ai_intent_planner.py`
- `backend/recommendations/services/ai_search_orchestrator.py`
- `backend/recommendations/services/conversation_sessions.py`
- `backend/recommendations/services/search_hard_gate.py`
- `backend/recommendations/test_conversation_sessions.py`
- `backend/recommendations/test_conversation_state_refinement.py`
- `backend/recommendations/test_general_search_contract.py`
- `backend/recommendations/test_result_quality_fallback.py`
- `backend/recommendations/services/conversation_patches.py`
- `backend/recommendations/test_conversation_quality_flows.py`

#### C2 근거·identity·진단 — 15파일

settings의 새 검색 flag와 제한 정책만 이 후보; IS_TESTING 위치 이동은 기능 변경이 아니므로 제외 가능. orchestrator/views/tests.py의 C2 hunk 동반. runtime 검색 v3 패키지는 공유 orchestrator에 미적용이며 이 후보에 자동 포함하지 않음.

- `backend/config/settings.py`
- `backend/recommendations/management/commands/analyze_identity_mismatches.py`
- `backend/recommendations/services/ai_web_search_provider.py`
- `backend/recommendations/services/kakao_local.py`
- `backend/recommendations/services/tag_evidence_aggregation.py`
- `backend/recommendations/test_tag_evidence_aggregation.py`
- `backend/recommendations/management/commands/report_tag_promotion_queue.py`
- `backend/recommendations/services/external_place_identity.py`
- `backend/recommendations/services/search_candidate_trace.py`
- `backend/recommendations/services/search_pipeline_metrics.py`
- `backend/recommendations/test_evidence_independence.py`
- `backend/recommendations/test_external_place_identity.py`
- `backend/recommendations/test_search_candidate_trace.py`
- `backend/recommendations/test_search_pipeline_metrics.py`
- `backend/recommendations/test_tag_promotion_queue.py`

#### C3 수집 결핍 우선순위 — 3파일

bootstrap_priority/search_coverage_demand와 해당 회귀. T1 및 master bounded planner의 정책 의미와 연결 검토.

- `backend/recommendations/services/bootstrap_priority.py`
- `backend/recommendations/services/search_coverage_demand.py`
- `backend/recommendations/test_search_coverage_demand.py`

#### C4 공개 제보·사용자 메시지 — 17파일

shared/user-message는 이미 master. serializer/views/tests.py는 대화/진단과 혼합이므로 공개 제보·메시지 hunk만 분리. 공통 화면 변경을 일괄 소유권/검증 주장으로 확대하지 않음.

- `backend/recommendations/serializers.py`
- `backend/recommendations/test_mobile_admin_workflows.py`
- `backend/recommendations/tests.py`
- `backend/recommendations/views.py`
- `frontend/src/views/AdminOperationsView.jsx`
- `frontend/src/views/AdminPlaceReportsView.jsx`
- `frontend/src/views/BoardCreateView.jsx`
- `frontend/src/views/BoardDetailView.jsx`
- `frontend/src/views/BoardEditView.jsx`
- `frontend/src/views/InquiryCreateView.jsx`
- `frontend/src/views/LoginView.jsx`
- `frontend/src/views/MyInquiryView.jsx`
- `frontend/src/views/MyPlaceReportsView.jsx`
- `frontend/src/views/MypageView.jsx`
- `frontend/src/views/PlaceReportView.jsx`
- `frontend/src/views/PreferenceSettingsView.jsx`
- `frontend/src/views/SearchHistoryView.jsx`

#### C5 웹 검색 UX — 20파일

shared/search-ux는 이미 master. MapSearchView/PlaceResultList 충돌 2개. API/session 계약과 generation/history/panel 변경을 C1 이후 검토; C7 빌드 연결 동반 필요.

- `frontend/src/api/recommendation.js`
- `frontend/src/api/recommendation.test.js`
- `frontend/src/hooks/homeSearchState.js`
- `frontend/src/hooks/useHomeSearch.js`
- `frontend/src/hooks/useSavedPlaceActions.js`
- `frontend/src/utils/aiWebSearchPolicy.js`
- `frontend/src/utils/homePlaceHelpers.js`
- `frontend/src/utils/kakaoPlaceRecommendation.js`
- `frontend/src/utils/placeResultConverters.js`
- `frontend/src/views/HomeView.jsx`
- `frontend/src/views/HomeView.test.jsx`
- `frontend/src/views/MapSearchView.jsx`
- `frontend/src/views/MapSearchView.module.css`
- `frontend/src/views/MapSearchView.test.jsx`
- `frontend/src/views/home/AiWebSearchPanel.jsx`
- `frontend/src/views/home/PlaceResultList.jsx`
- `frontend/src/hooks/useOverlayHistory.js`
- `frontend/src/hooks/usePanelHistory.js`
- `frontend/src/styles/SearchUx.css`
- `frontend/src/utils/searchUx.test.js`

#### C6 웹 알림 상태 — 2파일

웹 hook 및 새 회귀 2개만 잔여. 앱 알림 hook/화면/회귀는 이미 master이므로 이전 C6 모바일 범위 제거.

- `frontend/src/hooks/useNotifications.js`
- `frontend/src/hooks/useNotifications.test.jsx`

#### M1 앱 검색·대표 이미지 — 4파일

explore/recommend/reports/conversation 회귀 4파일. 기존 release 전체 기능은 재커밋 제외. 새 route 선택 참조/늦은 응답 무효화, 카테고리·중립 이미지 차이만 잔여. 4파일 모두 오래된 HEAD와의 3-way 충돌이므로 master 기준 차이만 선택.

- `mobile/src/app/(tabs)/explore.tsx`
- `mobile/src/app/(tabs)/mypage/reports.tsx`
- `mobile/src/app/(tabs)/recommend.tsx`
- `mobile/tests/ux/conversation.test.jsx`

#### M2 앱 계정 삭제 경합 — 2파일

기존 계정 삭제 route/설정 링크는 master에 존재. owner 전환 보호·중복 요청 guard와 mock 회귀 2파일만 후보. route add/add 충돌을 새 route 추가로 오인하지 않음.

- `mobile/src/app/account-deletion.tsx`
- `mobile/tests/ux/account-deletion.test.jsx`

#### C7 웹 빌드 연결 — 2파일

gateway shared COPY와 Vite .ts 해석 2파일. shared 모듈은 master에 있으나 미커밋 웹 import가 이를 사용하므로 C4/C5와 동반. mobile package/Metro/vitest config는 master과 같아 제외. 현재 CI의 앱 UX 실행 누락은 별도 변경 없으며 새 검증 요구로만 기록.

- `deploy/gateway/Dockerfile`
- `frontend/vite.config.js`

#### D1 모바일 안내 — 1파일

README 1파일의 최신 검증 안내·출시 코드 설명. 코드/스토어 완료 주장과 분리하여 해당 모바일 후보 문서로 동반.

- `mobile/README.md`

**이미 master과 동일한62개 목록:** 전체 원본 출시/수집 기능이 포함됐다는 원격 이력과 실제 현재 blob 비교를 구분했고, 아래는 현재 blob까지 일치한 경로다.

- `backend/recommendations/management/commands/recover_tag_collection_jobs.py`
- `backend/recommendations/models.py`
- `mobile/app.config.js`
- `mobile/eas.json`
- `mobile/package.json`
- `mobile/src/api/boards.ts`
- `mobile/src/api/client.ts`
- `mobile/src/api/recommendations.ts`
- `mobile/src/api/request-retry.ts`
- `mobile/src/app/(tabs)/_layout.tsx`
- `mobile/src/app/(tabs)/index.tsx`
- `mobile/src/app/(tabs)/mypage/index.tsx`
- `mobile/src/app/(tabs)/mypage/preferences.tsx`
- `mobile/src/app/(tabs)/mypage/saved-places.tsx`
- `mobile/src/app/(tabs)/mypage/search-history.tsx`
- `mobile/src/app/_layout.tsx`
- `mobile/src/app/admin/users/[userId].tsx`
- `mobile/src/app/admin/users/index.tsx`
- `mobile/src/app/boards/[boardType]/[postId]/index.tsx`
- `mobile/src/app/boards/[boardType]/index.tsx`
- `mobile/src/app/filter-search.tsx`
- `mobile/src/app/inquiries/new.tsx`
- `mobile/src/app/login.tsx`
- `mobile/src/app/notifications.tsx`
- `mobile/src/app/place-report.tsx`
- `mobile/src/app/settings.tsx`
- `mobile/src/app/signup.tsx`
- `mobile/src/app/upgrade-guide.tsx`
- `mobile/src/auth/auth-context.tsx`
- `mobile/src/components/bottom-nav.tsx`
- `mobile/src/components/place-detail-sheet.tsx`
- `mobile/src/components/place-map.tsx`
- `mobile/src/components/place-map.web.tsx`
- `mobile/src/components/place-photo.tsx`
- `mobile/src/components/post-editor.tsx`
- `mobile/src/components/report-detail.tsx`
- `mobile/src/components/screen.tsx`
- `mobile/src/hooks/use-action.ts`
- `mobile/src/hooks/use-resource.ts`
- `mobile/src/utils/place-identity.ts`
- `mobile/src/utils/place-report-labels.ts`
- `backend/recommendations/migrations/0032_collectionplannerstate_and_more.py`
- `backend/recommendations/services/collection_resources.py`
- `backend/recommendations/test_collection_resources.py`
- `mobile/metro.config.js`
- `mobile/src/hooks/use-form-draft.ts`
- `mobile/src/hooks/use-notifications.ts`
- `mobile/src/utils/back-navigation.ts`
- `mobile/src/utils/notification-settings.ts`
- `mobile/src/utils/notification-visibility.ts`
- `mobile/src/utils/saved-place-payload.ts`
- `mobile/src/utils/tier-display.ts`
- `mobile/tests/auth-recovery.test.cjs`
- `mobile/tests/form-draft.test.cjs`
- `mobile/tests/notification-visibility.test.cjs`
- `mobile/tests/saved-place-payload.test.cjs`
- `mobile/tests/tier-and-report-labels.test.cjs`
- `mobile/tests/ux/notifications.test.jsx`
- `mobile/tests/ux/setup.jsx`
- `mobile/vitest.ux.config.mjs`
- `shared/search-ux.ts`
- `shared/user-message.ts`

검증 재사용: 수집 통합94개 고유 검사(87+PostgreSQL7), 앱 Node22/UX13·TypeScript/lint 및 로컬 APK 설치는 각 최신 담당 보고서의 당시 후보 증거다. 이 Git 재분류는 코드 변경 없이 blob/충돌/보존을 검사했으며, 아직 만들지 않은 독립 master 후보의 테스트 성공으로 확대하지 않는다. 검색 A v3의90개 검사와 SQL10종/결과12종은 runtime 별도 패키지의 증거이고 현재 공유 코드와 분리한다. 전체 지연 수용/실제 운영 배포는 완료되지 않았다.

재현 자료: `runtime/dirty-reclassification-20261013/audit.json`, snapshot tree `1b606d9b646acc5700c924b2cb36d8be57225d27`. 공유 index·tracked/untracked 코드·현재 branch를 보존했고 commit/push/PR·운영 배포는 하지 않았다.

**다음 한 가지 행동:** master `84e3ebf7` 위에 T1 수집 P0 계측의 잔여9파일 hunk만 격리 후보로 구성하고 해당 후보의 관련 검사를 확인한다.


### T1 master 기반 격리 후보·관련 검사 완료

[T1 검토 보고서](T1_MASTER_CANDIDATE_REVIEW_2026-10-13.md)에 master `84e3ebf7` 대비9파일·716추가/25삭제 및 고정 tree `c70e09152b93db3d5bfa2d60c6577cc70c3ed9b0`를 기록했다. 관련94개 중87통과/PG7제외, system check/schema dry-run·9파일AST·diff check·master patch 적용검사 통과다. claim/settle/heartbeat AST 원본 유지, models/settings/migration/resources/recovery 및 다른 미커밋 기능은 master 원본이다. 공유소스hash 변경0·HEAD/index 유지·staged0, commit/push/PR·배포 없음. 이전 공유 통합본 PostgreSQL 성공을 이번 후보 직접 실행으로 확대하지 않는다.

**다음 한 가지 행동:** 검토된 T1 고정 tree를 독립 커밋·draft PR로 준비한다.


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


### PR #6 병합 후 최신 재분류 — master 9ab7e232 기준

원격 master를 별도 runtime bare 저장소에 받아 tip `9ab7e232ddb9049210caaad9e384a09a76084b08`를 고정했다. 공유 HEAD는 `6f1f8323cc87e3def055905a69e44c3af8322221`이며 이동하지 않았다. 최신 소스 hash를 이전147파일 snapshot과 비교한 결과 변경/추가/제거0으로, 검증한 blob147개를 재사용해 현재 master와 비교했다. 전체 기능 검사를 반복하지 않고 blob·격리 충돌·보존 검사만 수행했다.

| 구분 | 이전84e3ebf7 | 현재9ab7e232 | 해석 |
|---|---:|---:|---|
| 코드·설정·검사 총계 |147|147|공유 source 변화0|
| master과 내용 동일 |62|71|T1 9파일이 추가로 포함됨|
| 기존 master 파일 잔여 |64|59|T1 수정5파일 제외|
| master에 없는 신규 코드·검사 |21|17|T1 신규4파일 제외|
| 잔여 총계 |85|76|59+17, 아직 완성 commit이 아님|
| 격리3-way 충돌 |12|9|T1 3파일 충돌 해소, 새 충돌0|

현재 HEAD 대비 tracked 변경102개, runtime 제외 untracked73개(코드45/문서23/디자인5)다. 문서는 이전18개보다5개 늘었지만 코드 증가는 없다. runtime11,346파일·디자인5개는 기본 제외하며 전체 add하지 않는다. 기존62개 중복 목록은 이전 재분류 기록을 유지하고 아래9개를 추가 제외한다. 이미 master에 있는 로컬 미커밋 파일을 삭제/reset하지 않는다.

**T1 추가 제외9파일:**

- `backend/recommendations/management/commands/plan_daily_tag_collection.py`
- `backend/recommendations/management/commands/process_place_tag_collection_jobs.py`
- `backend/recommendations/management/commands/report_daily_collection.py`
- `backend/recommendations/management/commands/run_tag_collection_scheduler.py`
- `backend/recommendations/management/commands/summarize_collection_metrics.py`
- `backend/recommendations/services/bounded_collection_planner.py`
- `backend/recommendations/services/collection_telemetry.py`
- `backend/recommendations/test_bounded_collection_telemetry.py`
- `backend/recommendations/test_collection_telemetry.py`

**최신 충돌9파일:** 공유 옛 HEAD를 부모로 하는 dirty snapshot과 최신 master의 merge-tree 결과다. 공용 소스에는 충돌 마커를 쓰지 않았고, 이 결과를 커밋 후보로 사용하지 않는다. backend/settings 1개·웹2개·모바일 안내/화면/검사6개가 남았다. T1 worker/scheduler/bounded planner 충돌3개는 사라졌다.

- `backend/config/settings.py`
- `frontend/src/views/MapSearchView.jsx`
- `frontend/src/views/home/PlaceResultList.jsx`
- `mobile/README.md`
- `mobile/src/app/(tabs)/explore.tsx`
- `mobile/src/app/(tabs)/mypage/reports.tsx`
- `mobile/src/app/(tabs)/recommend.tsx`
- `mobile/src/app/account-deletion.tsx`
- `mobile/tests/ux/conversation.test.jsx`

**잔여 후보76파일 주분류:** 경로 목록은 중복 없이 세되 혼합 파일의 hunk는 위에서 설명한 계약대로 여러 후보에 나눠야 한다. C1/C2/C4는 파일 단위 독립성이 확정된 상태가 아니다.

| 후보 | 파일 수 | 분리·의존 조건 |
|---|---:|---|
|C1 대화 의미·엄격 조건|10|orchestrator는 C2와 혼합. views/tests.py는 C4에 주분류하되 session version/409 계약·대화 hunk는 C1에 동반한다. C5 검색 UX보다 먼저 계약 확정 필요.|
|C2 근거·identity·진단|15|settings의 새 검색 flag/상한은 여기 포함하고 IS_TESTING 위치 이동은 별도 기능 변경으로 세지 않는다. orchestrator/views/tests.py의 근거·진단 hunk와 연결. runtime 검색 A v3는 공유 source에 미적용이므로 자동 포함하지 않는다.|
|C3 수집 결핍 우선순위|3|T1과 CPU 기반은 이제 master에 포함됐다. bootstrap_priority/search_coverage_demand 정책·회귀 3파일만 잔여이며 master bounded planner와 의미 대조가 필요하다.|
|C4 공개 제보·사용자 메시지|17|shared/user-message는 이미 master이다. serializer/views/tests.py의 공개 제보·메시지 hunk만 선별하고 C1/C2 hunk를 분리한다. 화면별 검증과 서버 응답 계약을 동반한다.|
|C5 웹 검색 UX|20|shared/search-ux는 이미 master이다. MapSearchView/PlaceResultList 충돌2개를 보존 기준으로 처리하며 C1 계약 및 C7 빌드 연결과 함께 검증한다.|
|C6 웹 알림 상태|2|웹 useNotifications hook와 회귀2파일. 앱 알림 기능은 master와 동일하다. 계정 전환·늦은 응답 차단 회귀를 후보 고정 tree에서 확인한다.|
|M1 앱 검색·대표 이미지|4|explore/recommend/reports/conversation 회귀4파일. route 검색 선택 참조·generation/응답 guard·카테고리·중립 이미지 잔여만 분리한다. 4파일 모두 과거 HEAD 3-way 충돌이며 기능 결함4개라는 뜻은 아니다.|
|M2 앱 계정 삭제 경합|2|계정 삭제 route의 owner 전환/중복 요청 guard와 mock 회귀2파일. 기존 route·authStorage 등 기반은 master에 있어 C1/C2와 무관하게 분리 가능하다. 다음 격리 후보로 권장한다. 실제 삭제 요청 없이 검증한다.|
|C7 웹 빌드 연결|2|gateway shared COPY 및 Vite .ts 해석2파일. 새 웹 shared import를 쓰는 C4/C5에 동반하며 단독 기능 개선으로 분리하지 않는다. 모바일 package/Metro/vitest 설정은 이미 master이다.|
|D1 모바일 안내|1|README1파일의 최신 증거/출시 코드 안내. 해당 모바일 후보에 동반 가능하며 스토어·운영 완료 주장과 분리한다.|

#### C1 대화 의미·엄격 조건

- `backend/recommendations/services/ai_intent_planner.py`
- `backend/recommendations/services/ai_search_orchestrator.py`
- `backend/recommendations/services/conversation_sessions.py`
- `backend/recommendations/services/search_hard_gate.py`
- `backend/recommendations/test_conversation_sessions.py`
- `backend/recommendations/test_conversation_state_refinement.py`
- `backend/recommendations/test_general_search_contract.py`
- `backend/recommendations/test_result_quality_fallback.py`
- `backend/recommendations/services/conversation_patches.py`
- `backend/recommendations/test_conversation_quality_flows.py`

#### C2 근거·identity·진단

- `backend/config/settings.py`
- `backend/recommendations/management/commands/analyze_identity_mismatches.py`
- `backend/recommendations/services/ai_web_search_provider.py`
- `backend/recommendations/services/kakao_local.py`
- `backend/recommendations/services/tag_evidence_aggregation.py`
- `backend/recommendations/test_tag_evidence_aggregation.py`
- `backend/recommendations/management/commands/report_tag_promotion_queue.py`
- `backend/recommendations/services/external_place_identity.py`
- `backend/recommendations/services/search_candidate_trace.py`
- `backend/recommendations/services/search_pipeline_metrics.py`
- `backend/recommendations/test_evidence_independence.py`
- `backend/recommendations/test_external_place_identity.py`
- `backend/recommendations/test_search_candidate_trace.py`
- `backend/recommendations/test_search_pipeline_metrics.py`
- `backend/recommendations/test_tag_promotion_queue.py`

#### C3 수집 결핍 우선순위

- `backend/recommendations/services/bootstrap_priority.py`
- `backend/recommendations/services/search_coverage_demand.py`
- `backend/recommendations/test_search_coverage_demand.py`

#### C4 공개 제보·사용자 메시지

- `backend/recommendations/serializers.py`
- `backend/recommendations/test_mobile_admin_workflows.py`
- `backend/recommendations/tests.py`
- `backend/recommendations/views.py`
- `frontend/src/views/AdminOperationsView.jsx`
- `frontend/src/views/AdminPlaceReportsView.jsx`
- `frontend/src/views/BoardCreateView.jsx`
- `frontend/src/views/BoardDetailView.jsx`
- `frontend/src/views/BoardEditView.jsx`
- `frontend/src/views/InquiryCreateView.jsx`
- `frontend/src/views/LoginView.jsx`
- `frontend/src/views/MyInquiryView.jsx`
- `frontend/src/views/MyPlaceReportsView.jsx`
- `frontend/src/views/MypageView.jsx`
- `frontend/src/views/PlaceReportView.jsx`
- `frontend/src/views/PreferenceSettingsView.jsx`
- `frontend/src/views/SearchHistoryView.jsx`

#### C5 웹 검색 UX

- `frontend/src/api/recommendation.js`
- `frontend/src/api/recommendation.test.js`
- `frontend/src/hooks/homeSearchState.js`
- `frontend/src/hooks/useHomeSearch.js`
- `frontend/src/hooks/useSavedPlaceActions.js`
- `frontend/src/utils/aiWebSearchPolicy.js`
- `frontend/src/utils/homePlaceHelpers.js`
- `frontend/src/utils/kakaoPlaceRecommendation.js`
- `frontend/src/utils/placeResultConverters.js`
- `frontend/src/views/HomeView.jsx`
- `frontend/src/views/HomeView.test.jsx`
- `frontend/src/views/MapSearchView.jsx`
- `frontend/src/views/MapSearchView.module.css`
- `frontend/src/views/MapSearchView.test.jsx`
- `frontend/src/views/home/AiWebSearchPanel.jsx`
- `frontend/src/views/home/PlaceResultList.jsx`
- `frontend/src/hooks/useOverlayHistory.js`
- `frontend/src/hooks/usePanelHistory.js`
- `frontend/src/styles/SearchUx.css`
- `frontend/src/utils/searchUx.test.js`

#### C6 웹 알림 상태

- `frontend/src/hooks/useNotifications.js`
- `frontend/src/hooks/useNotifications.test.jsx`

#### M1 앱 검색·대표 이미지

- `mobile/src/app/(tabs)/explore.tsx`
- `mobile/src/app/(tabs)/mypage/reports.tsx`
- `mobile/src/app/(tabs)/recommend.tsx`
- `mobile/tests/ux/conversation.test.jsx`

#### M2 앱 계정 삭제 경합

- `mobile/src/app/account-deletion.tsx`
- `mobile/tests/ux/account-deletion.test.jsx`

#### C7 웹 빌드 연결

- `deploy/gateway/Dockerfile`
- `frontend/vite.config.js`

#### D1 모바일 안내

- `mobile/README.md`

검증: 현재 코드147파일 hash는 스냅샷 중·문서 기록 직전까지 유지, 공유HEAD/index hash 유지·staged0·tracked diff check 통과다. 고정 snapshot tree `1b606d9b646acc5700c924b2cb36d8be57225d27`는 이전 tree와 같고 master만 바뀌었다. 재현 자료는 `runtime/dirty-reclassification-post-t1-20261013/audit.json` 및 `candidates.json`이다. 이전 수집/모바일/검색 검사는 당시 코드·환경 증거로 유지하며, 아직 구성하지 않은76파일의 master 기반 독립 후보 검사 성공으로 확대하지 않는다.

이번 범위는 분류와 문서 갱신이다. 신규 제품 코드 수정·commit/push/PR/병합·운영 배포·설정/공유데이터/migration 실행은 하지 않았다.

**다음 한 가지 행동:** master `9ab7e232` 위에 M2 계정 삭제 경합2파일만 격리 후보로 구성하고 mock 회귀·관련 코드 검사를 확인한다.


### M2 master 기반 격리 후보·mock/코드 검사 완료

[M2 검토 보고서](M2_MASTER_CANDIDATE_REVIEW_2026-10-13.md): master9ab7e232 위에 삭제화면·mock2파일만 후보로 구성, tree `723f679b15b18e4fcfb8170e7f7477ce10b6277c`, 43추가/3삭제. 기존mock3개에 중복확인·요청직전계정전환2개를 후보안에서만 추가하고 import 순서정리. 최종mock5/5·인증Node6/6·격리TypeScript진단0·관련lint오류/경고0·patch apply/diffcheck 통과. 초기캐시EPERM은 허용환경mock으로 해소, 테스트lint는 기존웹dependency를 찾는 runtime resolver 사용. 클린설치/원본npm명령만의 검증은 아님. 공유147코드hash변경0·HEAD/index/staged0 유지, 실제삭제·commit/push/PR·운영배포 없음.

**다음 한 가지 행동:** 검토된 M2 고정 tree를 독립 커밋·draft PR로 준비한다.


### 잔여전체처리 — PR7병합/PR8통합후보검증완료

[검토보고서](REMAINING_INTEGRATION_REVIEW_2026-10-13.md)에76파일범위·4원본커밋·3-way결정·검증을기록했다. PR7원본0450db57병합masteraed267d6확인. PR8은원본3커밋/74파일·treecb604d5d로업로드/draft생성/연결했으며, 최종backend574통과19제외·web116/build·mobileUX15/Node22/타입/lint통과. master사용자문구/기존검사를보존해최초웹실패를해소했고T1blob9개유지. 공유source147hash변경0·HEAD/index/staged0유지·실제운영없음.

**다음 한 가지 행동:** PR8고정CI검토후원본이력유지병합·반영확인. 사용자전체처리승인으로계속진행한다.


### 잔여76파일전체통합완료

[최종보고](REMAINING_INTEGRATION_REVIEW_2026-10-13.md): PR7(0450db57/2files)·PR8(43047252/deead76a/a2ebafef/74files) 고정CI네job/실행단계success확인·원본유지병합. master745ef652·검토treecb604d5d정확일치, 원본4SHA조상검사·head→master파일차이0·시작9ab7e232대비76파일확인. 공유147sourcehash변경0·HEAD/index/staged0유지·운영미변경. 최초덮어쓰기후보의문구퇴행은3-way로해소하고원래검사보존,최종backend574통과19제외/web116/build/mobileUX15/Node22/types/lint. 요청Git통합남은작업없음;공유옛checkout dirty표시는보존결과다.


### 최종 master 병합 후 CI·최신 공유 변경 재분류

[보고서](POSTMERGE_LOCAL_RECONCILIATION_2026-10-13.md): master745ef652 push CI38349851893 네job/단계success·SHA일치확인. 최신코드148은동일131/통합보존차이15/신규N1 2파일이다. 새게시글사진파일제거와QA회귀는기존76통합후추가된범위로보존·미검증분류. 로컬문서30/디자인5/runtime14308은별도. 공유HEAD/index/staged0/hash유지,운영배포없음.

**다음한가지행동:** N1 2파일격리후보·mock/코드검사.


### 로컬 목록·완료복사본 정리 완료

[정리기록](LOCAL_WORKSPACE_CLEANUP_2026-10-13.md): runtime전체Git제외·완료복사본5곳12,684파일/188.84MiB삭제.85검토소스archive와Gitobjects/검사증거보존,진행중작업·공용deps·백업/산출물유지. 공유source/HEAD/index/staged0보존,최종Git목록189·runtime0. 원격반영코드의옛checkout표시는기존작업보존을위해유지,자동commit/운영변경없음.


### 최신 master 기준 공유 checkout 정리 완료

[정리보고서](LOCAL_MASTER_REBASELINE_2026-10-13.md): 사용자승인으로master745ef652 기준codex/shared-master-cleanup로로컬HEAD/index를맞춰이미반영된변경표시제거. 기존disk브랜치6f보존·새코드/검사5+ignore1·문서/디자인40=46개만잔여.71master소스복원/삭제0·3-way충돌0·hash보존/예상불일치0·staged0·diffcheck. 원격push/운영변경없음.


### 2026-10-14 남은 모바일·runtime 설정 — 로컬 고정 후보/승인 자료 완료

원격 쓰기를 묶은 부모 채팅 요청이 자동 승인 심사에서 명시 승인 부족으로 거절되어 원격 업로드·PR·master 병합은 실행하지 않았다. 원격읽기로master745ef652 유지를 확인했다. 모바일 담당 완료/인계manifest의5파일hash와현재/후보hash를대조해전부일치,최종APK buildsource128개일치다. 기존컴포넌트2+owner3·타입·관련lint·설치QA성공을재사용했고재빌드/검사반복없음.

저장소binkim00/life-infra-map, 제안branch codex/mobile-draft-photo-followup, base745ef65227546ac06754ab07c1287527c32792f4. source3/test2와.gitignore runtime1행 총6파일69추가/5삭제. 모바일5tree4065571e9430e5203ace3559c34005f3df40fb69,최종6tree d01896459898ca3aa1486cec14bda4251d48e25f. 실제commit SHA는없고공유HEAD/index/staged0유지. 두커밋계획(source5→ignore1),patch적용/diffcheck통과·선별private-key/AWS/GitHub/Slacktoken고신뢰패턴0·모의QA상수확인. 전수보안감사는아님.

runtime/mobile-approval-candidate-20261014의manifest.json/candidate.patch/approval-request.md/exclusions.json에고정후보·전체제외목록·PR제목/본문·정확한승인범위를기록했다. 런타임/APK/DB/원문로그/진행중보고서/디자인/과거patch제외,로그인문서의공개도메인→옛Tailscale퇴행도제외·로컬보존. 현재workflow는검사4job뿐이고원격승인후고정head/baseCI를확인해야한다. 외부webhook연계유무는미조회이며실제운영배포·설정/DB/migration·스토어제출은제외한다.

**다음 한 가지 행동:** 이 고정6파일/두커밋의 새branch업로드·draftPR생성과고정CI성공시원본유지master병합에대한명시승인을받는다.

## 2026-10-14 Git 최종 통합 — PR9 병합·직접 반영 검증 완료

- 사용자 직접 승인한 모바일5파일+.gitignore1파일만 codex/mobile-draft-photo-followup의 두 독립 커밋으로 업로드했다. 원본 323cd14589db29039535d3dff9f5e70a545e228d(모바일)와 3245fc604d1331760673123b9910557ea7152baf(runtime 제외)를 보존했다.
- PR https://github.com/binkim00/life-infra-map/pull/9 : draft 생성·첨부 후 CI 검토를 본문에 기록하고 ready 전환. head3245fc604d1331760673123b9910557ea7152baf/base745ef65227546ac06754ab07c1287527c32792f4, 2커밋/6파일/69추가5삭제 고정 확인 후 expected_head_sha 지정·merge 방식으로 병합했다. merged/closed 재조회 및 원격 master 1ef2e9ac5ff32098d250636ecd3474de133a6bcd 직접 일치.
- PR CI https://github.com/binkim00/life-infra-map/actions/runs/38488027108 completed/success. 웹115606299076(Node24 npm test/build), Spring115606299115(Java21 Gradle test), Django115606299300(Python3.12 accounts/boards/recommendations·test_settings), 앱115606299400(Node24 tsc/lint/Node glob) 모두 step 성공·고정 head 일치. 별도 push38488017327도 성공. 신규 owner3검사는 CI glob, UX adapter2검사는 이전 로컬검증으로 구분. check별 annotation1개 본문은 Code Review 연결 실패·generic fetch endpoint 미지원으로 조회하지 못했으며 실패 job/step은 없다.
- 격리 저장소에서 master tree d01896459898ca3aa1486cec14bda4251d48e25f=승인 tree 확인. base 대비 정확히6파일, PR head 대비 파일차이0, 원본 두 커밋 모두 master 조상 확인. publication 증거 runtime/mobile-approval-candidate-20261014/publication.json.
- 공유 소스6파일 SHA256 전부 유지, 공유 HEAD745ef652/index SHA256 08440b437967e3bacd4ab683aef8aa6aec97dcf396477539f615fd42e2f1a2e3/staged0 유지. 문서·디자인42개 및 runtime/백업 보존·원격 업로드 제외. 로컬48개 표시에는 이번 master 병합6개가 아직 포함된다. 공유 HEAD/index 보존 요구에 따라 추가 기준 전환은 하지 않았다.
- 실제 운영 배포·스토어 제출·운영 환경/서비스/DB/migration 변경 없음. 병합 후 새 master push CI는 이번 PR 고정 head/base CI 성공과 구분하며 완료를 아직 주장하지 않는다.
- 이번 승인 범위 필수 잔여0. 다음 한 가지 행동: 별도 요청 시 새 master의 병합 후 CI 또는 공유 로컬 기준 갱신을 확인한다. 앞선 Git 업로드/PR/병합 승인 대기 항목은 이 완료 기록으로 대체한다.
## 2026-10-14 수집 만료 후보 필터 Git 반영 — PR10 완료

- 직접 사용자 승인 수집4파일만 최신 master1ef2e9ac 위 독립 커밋 b0a97ee0ad57bb11bfd5e21a3f20cde6b8058c8f, tree1ec8854cfa91efce4e9e0f46301a5a213ff4c8af로 고정. 대상 backend/recommendations/services/tag_freshness.py, services/place_tag_collection.py, services/naver_tag_evidence_provider.py, test_collection_freshness.py. 기존3서비스의 공유HEAD→최신master 차이0 확인, 신규4파일만 포함·108추가10삭제. TTL/identity/자동승인/DB/API호출수 변경없음. 기존64검사 성공기록 확인·후보 whitespace 통과.
- PR https://github.com/binkim00/life-infra-map/pull/10 생성·첨부·CI검토본문기록·ready 뒤 expected_head_sha b0a97ee0 지정 merge 방식으로 병합. merged/closed 재조회 및 원격 master c58d885c52ddf65095e1d28efb0fdc4015e6b9ba 직접 fetch 확인. 원본 커밋 조상 유지, master tree=승인tree, base 대비 정확히4파일·head 대비 파일차이0.
- 고정head PR CI https://github.com/binkim00/life-infra-map/actions/runs/38494557277 : Spring115627253689(Java21 Gradle test), 웹115627253801(Node24 test/build), Django115627253875(Python3.12 accounts/boards/recommendations test_settings·신규6포함), 앱115627253935(Node24 tsc/lint/Node test) 모두 completed/success·check SHA 일치. 각 annotation1개는 Ubuntu26 runner 전환예고 notice이며 오류없음. 운영/native/store검증 아님. 새master 병합후push CI 완료는 별도미확인.
- 공유4파일 SHA256/HEAD745ef652/index08440b43.../staged0 보존. 모바일/문서/runtime/산출물 업로드 제외. 증거 runtime/collection-freshness-git-20261014/publication.json·candidate.patch. 후보준비 중 격리 Git alternates CRLF·기준미지정diff를 보정했고 공유변경없음.
- Git 필수잔여0. 이채팅 운영변경0. 다음 한 가지 행동: 수집 담당이 승인된 별도배포 범위에서 원본 b0a97ee0의4파일만 현재운영image에 선별반영·검증한다. 실측품질향상은미측정.
