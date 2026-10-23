# 공유 작업 보존·최신 master 기준 로컬 정리 — 2026-10-13

사용자가 이미 반영된 변경을 미커밋 목록에서 제외하고 새 변경과 문서를 보존하도록 승인했다. 원격 master를 두 번 읽어 `745ef65227546ac06754ab07c1287527c32792f4`가 유지됨을 확인한 뒤 로컬 기준을 맞췄다. 원격 push·운영 배포·서비스/설정/DB/migration 실행·스토어 변경은 하지 않았다.

## 완료 결과

- 현재 로컬 branch: `codex/shared-master-cleanup`
- 현재 HEAD 및 origin/master: `745ef65227546ac06754ab07c1287527c32792f4`
- 기존 `codex/disk-maintenance`: `6f1f8323cc87e3def055905a69e44c3af8322221` 그대로 보존
- 공용 index는 최신 master tree를 기준으로 갱신했고 새 변경은 staged0으로 남겼다.
- 보고서 생성 전 목록189→45개, 본 보고서1개 추가 후46개다. runtime 표시0을 유지한다.

## 남겨둔 변경

master에 없는 새로운 코드·검사5개를 그대로 보존했다.

1. `mobile/src/app/place-report.tsx`
2. `mobile/src/components/post-editor.tsx`
3. `mobile/src/utils/place-report-draft.ts`
4. `mobile/tests/report-owner-draft.test.cjs`
5. `mobile/tests/ux/audit-20261013.test.jsx`

사진 제거·관리 파일 정리와 계정별 제보 초안/사진 분리 관련 후속 변경이다. 이번 요청은 Git 기준 정리이며 이 새 변경의 제품 수정·추가 기능 검사·commit/push/PR은 실행하지 않았다. 기존 `.gitignore`의 `/runtime/` 추가도 미커밋 상태로 보존했다.

문서·디자인 자료는 본 보고서를 포함해40개다. tracked 문서 `docs/00_project/social-login-setup.md`와 로컬 검증/통합/운영 보고서·역사적 patch·디자인 초안을 포함한다. 기존 문서 바이트를 수정/삭제하지 않았고, 새 master에만 있던 누락된 tracked 문서는 복원했다. 이 문서들은 사용자 요청에 따라 별도 미커밋 검토 대상으로 남긴다. 코드6개(새5+ignore1)와 문서/디자인40개를 합치면46개다.

## 보존과 적용 방식

이미 통합한 공유 snapshot을 공통 기준으로 삼아 현재 새 변경만 최신 master 위에 3-way 결합했다. 과거 공유 파일 전체를 그대로 다시 적용하거나 새 변경을 없애는 reset/clean/stash를 사용하지 않았다. 격리 후보는 충돌0으로 생성됐다. 새 코드·검사와 기존 문서는 작업 전 바이트 그대로 유지한다.

현재 파일의 hash를 기록하고, 바뀔 기존 파일은 [before-files.zip](../runtime/master-rebaseline-20261013/before-files.zip)에 복원용으로 보관했다. 기존 index도 before-index.bin으로 보존했다. [plan](../runtime/master-rebaseline-20261013/plan.json)과 prepared-files.zip은 대상·hash·미리 검증한 후보를 기록한다. 각 파일은 적용 직전 hash를 다시 확인해 다른 작업이 먼저 수정했다면 중단하도록 했다.

master의 기존 코드·기능·설정·검사·소스 문서71파일을 적용/복원했고 삭제 파일0이다. 실사용 환경 파일·비밀키·DB는 변경하지 않았다. 업데이트에 포함된 `.env.example`은 master의 소스 예제이며 운영 `.env`를 읽거나 적용한 것이 아니다.

원격 ref는 바꾸지 않고 runtime bare 저장소에서 최신 master objects를 로컬에 받아 origin/master를 맞췄다. 새 로컬 branch를 master에 만들고 index 기준을 갱신한 뒤 HEAD를 전환했다. 기존 branch 이름과 commit은 그대로 남겨 복원 가능한 이력을 유지했다.

## 검증

[verification](../runtime/master-rebaseline-20261013/verification.json)의 적용 후 hash 대조에서 보존/계획 불일치0, 기존 branch tip 유지, 새 HEAD745ef652, staged0, diff whitespace 검사 통과를 확인했다. 최초 제한 환경의 Git helper 실행 오류는 동일 읽기 검증을 허용 환경에서 수행해 해소했다. 코드 기능 검사를 새로 통과했다고 주장하지 않으며 master의 이전 병합 후CI 증거와 새 미커밋 변경의 검증 범위를 분리한다.

본 결과 문서와 CODEX_STATE/Git 통합 계획 milestone만 추가 갱신한다. 이미 반영된 source가 미커밋 목록에서 사라지고 새 작업이 남도록 하는 이번 요청은 완료했다. 화면에 옛189개가 남으면 Git 상태를 새로고침하면 된다.
