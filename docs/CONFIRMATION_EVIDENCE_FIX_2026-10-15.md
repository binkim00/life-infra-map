# 확인 태그 현재 근거 검사 — 로컬 수정·검증 완료

2026-10-15. 사용자는45개태그문제의로컬수정/검증만승인했으며DB/기존서비스변경금지. 이번작업에서SSH/AWS/운영DB/API접속없음. migration/재집계/승인변경/배포/commit/push없음. 테스트용SQLite :memory:만사용.

## 동작

- materialized PlaceTag의 checked/user_verified를 일반추천 get_place_tag_data와대화검색 _db_tag_lists가읽을때동일place/tag의현재유효positive Evidence가있는지검사한다.
- approved근거또는review없는비웹근거만허용한다. 관리자/사용자직접관측의기존무기한정책은유지하며,웹은공통hard gate와동일하게승인을요구한다. 현재양성유효성만검사하며기존수동승인/독립출처승격정책을새로재집계하지않는다.
- 근거없음/만료/보류/반려/제한승인/부정만있음이면해당checked/user_verified행을현재태그목록과tag_details에서제외한다. suggested/candidate/warning으로우회노출하지않고,근거없는상태에새historical정보를만들지않는다. 기존historical web aggregate와다른source행은그대로다.
- 저장is_verified/status/수동검토이력/관측일/만료일은갱신하지않는다. 같은이름의다른유효태그행은유지한다.
- 일반추천및대화검색의후보묶음prefetch에서Case/Exists로관련근거를함께주석처리해태그당조회증가를막는다. 단독helper호출도필요한확인태그만한번에조회한다.
- 대상은checked/user_verified파생확인태그뿐이다. 다른원천field_rule/external_data의수명정책,주소판정,보류재심사,근거충돌판정은변경하지않았다. API모든경로/실제운영45개행수정효과는운영반영전미검증.

## 파일

- backend/recommendations/services/confirmation_evidence.py 신규읽기전용공통검사.
- backend/recommendations/services/db_recommender.py 및ai_search_orchestrator.py 두reader/후보prefetch연결.
- backend/recommendations/test_confirmation_evidence.py 신규16검사.

## 검증

- 신규16+기존근거집계/모바일관리자26=42개통과.
- DB후보조회/공통hardgate/대화품질/결과fallback/근거독립성101개통과. 합계143개.
- 두reader의누락·만료·만료경계·negative·다른장소/태그·미승인웹·pending/rejected/approved_limited/research·is_verified=false confirmed우회차단검증.
- 관리자/사용자직접관측·무기한관측·현재approved웹·새근거로대체·동명이름타source유효확인보존검증.
- 읽기중SQL은SELECT뿐이고저장Tag/Evidence/Review필드전후동일검사통과. 여러place묶음은2queries(Place+태그/관련Exists)로양쪽reader호출완료확인.
- config.test_settings로SQLite :memory:사용. 첫42실행중기존manifest테스트1개가sandbox기본임시디렉터리권한으로오류. TMP/TEMP를workspace runtime/confirmation-fix-20261015/temp로옮긴후동일42개전부통과. 제품코드를권한오류에맞춰바꾸지않았다.
- git diff --check통과. 원래수집신선도3개수정/신규검사등다른작업변경보존. 광범위전체suite/실제PostgreSQL성능/모바일실화면/운영검증없음.

근거 runtime/confirmation-fix-20261015/{targeted-tests,search-regression-tests}.txt. 다음한가지행동: 운영반영을원하면이4파일의분리검토부터진행한다. 현요청의로컬수정/검증은완료.


## 2026-10-23 미커밋 작업 분리 검증

- 기준: origin/master 45f0c109, 로컬 codex/uncommitted-work-audit. 배포/DB 변경 없음.
- SQLite 메모리 설정으로 accounts/boards/recommendations 전체 1,182개 실행 성공, 조건부 제외 28개. 신규 근거 검사 16개 포함.
- 최초 실행의 정상 확인 태그 fixture 누락으로 기존 검색 검사 7개 실패. 해당 정상 사례에만 현재 admin_review positive 근거를 추가했고 기존 기대 결과/검증 조건은 유지했다.
- 원본 공유 폴더를 수정하지 않고 분리된 작업 폴더에 6개 파일을 커밋한다. 원격 CI/운영 PostgreSQL 성능은 이번에 검증하지 않았다.
- 실행 로그: 원본 작업 폴더 runtime/uncommitted-audit-20261023/confirmation-final-tests.txt.
