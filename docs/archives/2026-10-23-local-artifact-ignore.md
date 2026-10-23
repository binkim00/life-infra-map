# 로컬 산출물 제외 규칙 정리

2026-10-23. 원래 미커밋 .gitignore의 /runtime/, /qa14/, /.cxx-build/ 세 규칙만 보존했다. 진단 로그·QA 산출물·Windows 네이티브 중간 빌드 디렉터리를 추적에서 제외한다.

검증: git check-ignore --no-index로 위 세 디렉터리 하위가 제외되고 mobile/src/audit-probe.ts는 제외되지 않음을 확인했다. 실제 파일은 만들거나 삭제하지 않았다. 기존 추적 파일/원래 작업 폴더 index는 변경하지 않았다.
