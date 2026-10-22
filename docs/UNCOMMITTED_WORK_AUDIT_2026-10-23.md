# 미커밋 작업 분류·분리 커밋 — 2026-10-23

## 범위와 결과

- 기준 master: `45f0c109feb1badd906ee9e5680a60fac3b8b27e`. 원본 공유 checkout: `codex/shared-master-cleanup` / `745ef65227546ac06754ab07c1287527c32792f4`.
- 로컬 커밋 브랜치: `codex/uncommitted-work-audit`. 작업 폴더: `C:/Users/SSAFY/.codex/worktrees/address-identity-release/life-infra-map`.
- 원래 대기 파일 111개 중 master 동일 사본 29개, 다른 브랜치 동일 사본 11개, 끝 빈 줄만 다른 사본 1개, 신규 완료 작업/기록 65개, 미선정 아이콘 시안 5개로 분류했다.
- 신규 65개만 관련 테스트·기록과 함께 분리 커밋했다. 추가로 기존 정상 검색 테스트 fixture의 현재 근거를 명시하고 분야별 기록 색인을 작성했다. 과거 설계 문서의 작성 완료를 그 설계의 실제 구현·배포 완료로 취급하지 않았다.
- 원래 111개 파일 SHA256, 공유 HEAD, 비어 있던 공유 staging index 모두 보존했다. 원본 폴더에서 변경 사본은 계속 미커밋으로 보일 수 있으며 삭제/리셋/숨김 처리하지 않았다.
- 이번에는 push/PR/merge/배포/운영 접속/설정·DB 변경/보류 해제를 하지 않았다. 새 CI나 네이티브 AAB 빌드·스토어 검증도 하지 않았다.

## 작업별 커밋

| 커밋 | 작업 |
| --- | --- |
| `69e9492ea5616bf972e9a84bc3a5e91f0f81afbd` | fix: require current evidence for confirmation tags |
| `9d4fc016911fad68f4da79f2b16788deec946cc5` | fix: preserve legacy Android window behavior in release guard |
| `c4aba94dd3d3739ee3adc30845bb9b65284a0ca0` | feat: add draggable mobile search results panel |
| `ce0ac87ceca4607b0f6456d8e09bfcd50a8ccb03` | docs: preserve collection telemetry and validation history |
| `10136ae50bc57768dce8b3df6391d62027caa5f1` | docs: preserve search quality and performance reviews |
| `4d5ccd252be3cfd43f3d021bd82ce4b2838118ef` | docs: preserve read-only evidence and address audits |
| `eebfb32a5f3e84c4b4c5ef218a9b70c01fbd3a50` | docs: preserve mobile QA and tester preparation records |
| `7012e425f7d8c039e8659d967faeaba2f3708b86` | docs: preserve isolated integration and repository reviews |
| `05c1c7e159d8140c071eb4dafc9192c5f8da11a2` | docs: preserve read-only observability assessment |
| `cd4bcb217ae31f75298fa92f728cd1fa4f3bb029` | chore: ignore local diagnostic and native build artifacts |

이 보고서 자체는 마지막 독립 문서 커밋에 포함된다. 각 구현 커밋에는 해당 테스트와 검증 결과를 기록한 문서가 포함된다.

## 이번 검증

- Django: accounts/boards/recommendations 전체 1,182개 실행 성공, 조건부 제외 28개. 신규 confirmation 검사 16개 포함. SQLite 메모리 DB만 사용했다.
- 최초 실행에서 기존 정상 확인 태그 fixture에 근거가 없어 검색 검사 7개 실패. 정상 근거를 해당 fixture에만 추가하고 기존 assertion과 제품의 근거 기준은 유지했다. 최종 전체 검사 성공.
- 모바일: 일반 Node 25개, UX 19개 통과. TypeScript noEmit/Expo lint 성공. 기존 의존성을 사용했고 설치/버전 갱신 없음.
- Android: 플러그인 JS 구문 검사, 현재 Java 컴파일/변환된 바이트코드의 SDK 24/28/34/35/36 다섯 검사 통과. 기본 제한 환경 Java 시간 초과 뒤 허용된 분리 작업 폴더에서 성공했다.
- 신규 커밋 파일의 UTF-8/개인 키·AWS/GitHub 토큰 패턴 검사 통과. 문서 공백 검사 통과. 보존용 패치 2개는 git apply --numstat 구문 검사 통과, 과거 문맥 공백을 보존했고 현재 코드에 적용하지 않았다.
- 승인한 소스/설정의 최종 Git blob이 원본 미커밋 파일과 같음을 대조했다. 문서는 최종 공백 정리와 새 검증 절/색인 외 과거 한계를 유지했다.
- 로그/원본 해시 목록은 공유 폴더 `runtime/uncommitted-audit-20261023/`에 로컬 보관한다. 실행 로그나 빌드 산출물은 커밋하지 않았다. 과거 문서의 운영 수치·외부 링크·runtime 원본은 이번에 모두 재검증한 것이 아니다.

## master와 같은 사본 — 재커밋 제외

- `.gitattributes`
- `backend/recommendations/services/automatic_content_review.py`
- `backend/recommendations/services/naver_tag_evidence_provider.py`
- `backend/recommendations/services/place_tag_collection.py`
- `backend/recommendations/services/tag_freshness.py`
- `mobile/src/app/place-report.tsx`
- `mobile/src/components/post-editor.tsx`
- `mobile/src/utils/place-report-draft.ts`
- `backend/recommendations/fixtures/address_identity_acceptance.json`
- `backend/recommendations/services/address_details.py`
- `backend/recommendations/services/address_identity.py`
- `backend/recommendations/test_address_identity.py`
- `backend/recommendations/test_address_matching.py`
- `backend/recommendations/test_collection_freshness.py`
- `docs/ADDRESS_IDENTITY_REFACTOR_2026-10-23.md`
- `docs/ADDRESS_MATCHING_FINAL_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_LOCAL_FIX_2026-10-22.md`
- `docs/ADDRESS_MATCHING_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_V10_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_V11_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_V12_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_V13_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_V14_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_V15_REVIEW_2026-10-23.md`
- `docs/ADDRESS_MATCHING_V7_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_V8_REVIEW_2026-10-22.md`
- `docs/ADDRESS_MATCHING_V9_REVIEW_2026-10-22.md`
- `mobile/tests/report-owner-draft.test.cjs`
- `mobile/tests/ux/audit-20261013.test.jsx`

## 다른 브랜치에 보존된 사본 — 재커밋 제외

`docs/00_project/social-login-setup.md`는 과거 로컬 브랜치의 사본이다. 현재 master를 이 오래된 내용으로 되돌리지 않았다. observability 파일은 `origin/codex/observability-and-migration-20261015`의 기존 커밋 `123e7c4b`에 보존된 사본이며 master 통합 완료를 뜻하지 않는다.

- `docs/00_project/social-login-setup.md` — `refs/heads/codex/disk-maintenance`, `refs/heads/codex/service-flow-verification`, `refs/remotes/origin/codex/disk-maintenance`
- `deploy/observability/.gitignore` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/README.md` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/compose.json` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/compose.metrics.json` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/db_fingerprint.py` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/install_metrics.py` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/loki.json` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/mount_clone.py` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/prepare.py` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/prepare_clone.py` — `refs/remotes/origin/codex/observability-and-migration-20261015`
- `deploy/observability/MIGRATION.md` — 같은 observability 브랜치와 끝 빈 줄만 다름.

## 미완료·미선정 상태로 보존

- `docs/ui-concepts/app-icon-draft-01.png` — 미선정 시안, 커밋 제외.
- `docs/ui-concepts/app-icon-draft-02.png` — 미선정 시안, 커밋 제외.
- `docs/ui-concepts/app-icon-draft-03-cards.png` — 미선정 시안, 커밋 제외.
- `docs/ui-concepts/app-icon-draft-05-selection.png` — 미선정 시안, 커밋 제외.
- `docs/ui-concepts/app-icon-draft-06-recommendation.png` — 미선정 시안, 커밋 제외.

## 새로 커밋한 원본 파일

- `.gitignore`
- `backend/recommendations/services/ai_search_orchestrator.py`
- `backend/recommendations/services/db_recommender.py`
- `mobile/app.json`
- `mobile/src/app/(tabs)/explore.tsx`
- `backend/recommendations/services/confirmation_evidence.py`
- `backend/recommendations/test_confirmation_evidence.py`
- `docs/ADDRESS_HOLD_DIAGNOSIS_2026-10-15.md`
- `docs/ADDRESS_HOLD_SAMPLE_AUDIT_2026-10-22.md`
- `docs/APP_COLLECTION_CHECK_2026-10-15.md`
- `docs/COLLECTION_FRESHNESS_RELEASE_2026-10-14.md`
- `docs/COLLECTION_LIMITED_OBSERVATION_PLAN_2026-10-13.md`
- `docs/COLLECTION_OPERATION_START_BASELINE_2026-10-13.md`
- `docs/COLLECTION_P0_DEPLOYMENT_CANDIDATE_2026-10-13.md`
- `docs/COLLECTION_P0_QUALITY_CAUSE_2026-10-13.md`
- `docs/COLLECTION_P0_RELEASE_2026-10-13.md`
- `docs/COLLECTION_POSTGRES_VALIDATION_2026-10-13.md`
- `docs/COLLECTION_QUALITY_FOLLOWUP_2026-10-13.md`
- `docs/COLLECTION_TELEMETRY_INTEGRATION_2026-10-13.md`
- `docs/COLLECTION_TELEMETRY_P0_2026-10-13.md`
- `docs/CONFIRMATION_EVIDENCE_FIX_2026-10-15.md`
- `docs/FULL_DATA_AUDIT_2026-10-15.md`
- `docs/GIT_INTEGRATION_PLAN_2026-10-13.md`
- `docs/GRAFANA_LOKI_PLAN_2026-10-14.md`
- `docs/LOCAL_MASTER_REBASELINE_2026-10-13.md`
- `docs/LOCAL_WORKSPACE_CLEANUP_2026-10-13.md`
- `docs/M2_MASTER_CANDIDATE_REVIEW_2026-10-13.md`
- `docs/MOBILE_APK_INSTALL_VERIFICATION_2026-10-13.md`
- `docs/MOBILE_FULL_QA_2026-10-13.md`
- `docs/MOBILE_INTEGRATION_REVIEW_2026-10-13.md`
- `docs/MOBILE_PLAY_WARNINGS_2026-10-14.md`
- `docs/MOBILE_SEARCH_PANEL_QA_2026-10-16.md`
- `docs/MOBILE_SEARCH_PANEL_RELEASE_2026-10-16.md`
- `docs/MOBILE_STORE_READINESS_2026-10-13.md`
- `docs/NAVER_PLACE_EVIDENCE_SEARCH_COMPARISON.md`
- `docs/PLAY_TESTER_PREPARATION_2026-10-14.md`
- `docs/POSTMERGE_LOCAL_RECONCILIATION_2026-10-13.md`
- `docs/READ_ONLY_QUALITY_AND_EVIDENCE_AUDIT_2026-10-22.md`
- `docs/REGIONAL_MEANINGFUL_EVIDENCE_2026-10-15.md`
- `docs/REMAINING_INTEGRATION_REVIEW_2026-10-13.md`
- `docs/SEARCH_CONVERSATION_QUALITY_REPORT.md`
- `docs/SEARCH_EVIDENCE_PIPELINE_COMPLETION_2026-10-06.md`
- `docs/SEARCH_EVIDENCE_VALUE_DIAGNOSIS_2026-10-06.md`
- `docs/SEARCH_FINAL_CLOSEOUT_2026-10-14.md`
- `docs/SEARCH_HYDRATION_REPEAT_REVIEW_2026-10-13.md`
- `docs/SEARCH_PACKAGE_A_REVALIDATION_2026-10-13.md`
- `docs/SEARCH_PACKAGE_A_VALIDATION_2026-10-13.md`
- `docs/SEARCH_PIPELINE_RELEASE_REVIEW_2026-10-13.md`
- `docs/SEARCH_PREPARED_EVIDENCE_REVIEW_2026-10-13.md`
- `docs/SEARCH_SEOUL_INDEX_ISOLATED_REVIEW_2026-10-13.md`
- `docs/SEARCH_SEOUL_PG164_VISIBILITY_REVIEW_2026-10-13.md`
- `docs/SEARCH_SEOUL_SQL_TAIL_REVIEW_2026-10-13.md`
- `docs/SEARCH_UX_COMPLETION_REPORT.md`
- `docs/SERVER_GIT_REFLECTION_PLAN_2026-10-15.md`
- `docs/T1_MASTER_CANDIDATE_REVIEW_2026-10-13.md`
- `docs/operations/collection-telemetry-bounded-76e2.patch`
- `docs/operations/collection-telemetry-resource-76e2.patch`
- `mobile/plugins/android-api-guards/ReactNativeWindowApiGuard.java`
- `mobile/plugins/android-api-guards/tests/GuardCheck.java`
- `mobile/plugins/android-api-guards/tests/GuardFixture.java`
- `mobile/plugins/android-api-guards/tests/android/os/Build.java`
- `mobile/plugins/android-api-guards/tests/android/view/Window.java`
- `mobile/plugins/with-android-release-optimization.js`
- `mobile/src/components/search-results-panel.tsx`
- `mobile/tests/ux/search-results-panel.test.jsx`

## 다음 행동

추가 게시·통합 요청 전에는 이 로컬 브랜치를 유지한다.
