# 로컬 Git 목록·완료된 검증 복사본 정리 — 2026-10-13

사용자가 정리와 삭제를 요청했다. `.gitignore`에 `/runtime/`을 추가해 검사 dependency·격리 소스·임시 증거가 미커밋 목록에 나타나지 않도록 했다. runtime의 tracked 파일은 없음을 확인했으며 ignore로 소스나 기존 Git 이력을 삭제하지 않았다. 이 설정 변경은 미커밋 상태이고 공용 index에 올리지 않았다.

## 삭제한 범위

완료된 고정 후보·원본 SHA에서 다시 만들 수 있는 복사본만 선별했다. 대상 절대경로가 workspace/runtime 내부임을 확인하고 실행 중 python/node/java/git 프로세스의 경로 참조가 없는지 검사했다. 네 dependency junction은 연결만 해제한 뒤 복사본을 삭제했다. 공유 node_modules로 재귀 삭제하지 않았다.

| 대상 | 삭제 파일 | 파일 크기 합계 |
|---|---:|---:|
| runtime/pr3-fixed-head-review |149|5,781,985 bytes|
| runtime/t1-master-candidate-20261013/candidate |3,951|41,225,805 bytes|
| runtime/m2-master-candidate-20261013/candidate |146|5,799,083 bytes|
| runtime/remaining-integration-20261013/candidate |4,491|104,058,058 bytes|
| runtime/collection-fixed-head-review/backend |3,947|41,149,675 bytes|
| 합계 |12,684|198,014,606 bytes / 188.84 MiB|

선택된 다섯 폴더의 삭제 완료·공유 모바일 TypeScript 및 웹 Vitest dependency 존재를 확인했다. 삭제된 수에는 Git이 이미 제외하던 캐시 등도 포함돼 이전 미커밋 수와 일대일 대응하지 않는다.

## 보존한 범위

- 공유 backend/frontend/mobile/shared/deploy/scripts의 기존 tracked/untracked 코드와 새 미커밋 수정
- 진행 중인 mobile-full-audit·search-index/search-package·P0 관찰/복구·모바일 설치 검증 자료
- 공용 test-deps/test-venv, node_modules, 백업, 유일한 빌드·배포/복구 패키지
- fixed commit objects/bare 저장소/alternates, patch·manifest·검사 로그·audit 등 재현 증거

검토된 T1/M2/잔여 후보 소스85개는 삭제 전에 [reviewed-source-snapshots.zip](../runtime/cleanup-evidence-20261013/reviewed-source-snapshots.zip)에 압축했다. 약463.8 KiB이며 archive CRC와 각 entry SHA256을 대조했다. 원본 Git objects도 남아 있어 고정tree에서 전체 후보를 다시 추출할 수 있다. 이전 보고서의 삭제된 candidate source 링크는 이 archive 또는 GitHub 고정 commit을 사용하며 검사 결과 링크는 보존했다.

[삭제 계획·원본 hash](../runtime/cleanup-evidence-20261013/cleanup-plan.json), [삭제 결과](../runtime/cleanup-evidence-20261013/deletion-results.json), [최종 보존·Git 목록 audit](../runtime/cleanup-evidence-20261013/final-audit.json)에 기록한다.

## Git 화면과 남은 표시

정리 직후·본 보고서 생성 전 Git 기준은 tracked 변경104 + untracked83 =187파일이며 runtime 표시0이다. 본 보고서와 공유 작업 중 추가된 파일을 포함한 최종 확인값은189개다. 화면의 cached count는 새로고침 후 반영될 수 있다. 이는 프로젝트 소스가 새로 늘어난 수나 남은 개발188건이 아니다.

이미 master에 반영된 코드도 공유checkout이 이전HEAD6f1f8323 기준이므로 수정 표시가 남는다. 새 작업과 여러 작업의 공유 파일을 보존하기 위해 checkout/reset/clean/stash·HEAD/index 전환은 하지 않았다. 이 차이를 없애려고 전체 stage/소스 삭제/덮어쓰기를 하지 않는다. 기존 master 반영분·보존차이·새 코드 구분은 [병합 후 재정리 보고서](POSTMERGE_LOCAL_RECONCILIATION_2026-10-13.md)를 따른다.

이번 요청의 목록 정리·완료된 임시 복사본 삭제는 완료했다. 추가 `.gitignore` 변경과 본 보고서는 정상적인 미커밋 정리 결과다. 자동 commit/push/PR·운영 배포·실제 계정 삭제·서비스/설정/공유 DB·migration·스토어 변경은 없다.
