# 검색 개선·인덱스 실험 최종 종료 — 2026-10-14

## 최종 결정

**검색 담당의 구현·검증·실험 정리는 완료. 인덱스 후보는 채택하지 않고 실험을 종료한다. 추가 최적화와 운영 인덱스 적용 계획을 필수 잔여 작업으로 두지 않는다.**

선별 검색 패키지 A의 v6는 검증된 로컬 후보로 보존한다. “운영 v6 유지”라는 표현은 부정확하다. 운영은 현재도 기존 기준본이며 v6 배포를 확인한 적이 없다. 2026-10-14 SSM 읽기 전용 해시 재조회가 Success/exit0, stderr 없음으로 이를 확인했다. 운영 파일·인덱스·설정·서비스·데이터를 변경하지 않았다.

## SHA별 완료 범위

| 대상 | 정확한 SHA / 식별자 | 의미 |
|---|---|---|
| 선별 v6 orchestrator | `7fca56232ddfb021b92bc6ec88e31771b7caf04f6d0fadc5bd6df79a07279510` | 로컬 패키지·격리 회귀·메모리 비교의 후보 파일 SHA256. CI/master/운영 반영 증거가 아님 |
| v6 archive | `9904ed0a4ae2388337b344a094cf59ef2ee125afdf72db8518455e34879fe7f9` | 보존 tar.gz SHA256 재검증 |
| 패키지 base / rollback / 현재 운영 | `cc265e7968bfc8e1d2bfb689acd1ed257fc2c9095335ca8eaf005d0e1ad1972d` | rollback 파일 hash와 새 운영 조회가 일치. 실제 rollback 실행은 하지 않음 |
| 별도 통합 backend commit | `430472527ac5bbd2cf58cb5d26e6063faef7e1f2` | 32파일의 대화·근거·수집 우선순위·제보 계약 통합. v6 전용 패키지와 다른 범위 |
| PR8/master 고정 commit | `745ef65227546ac06754ab07c1287527c32792f4` | backend 원본430472의 조상 관계 exit0 확인. 현재 HEAD/origin/master의 로컬 읽기 기준 |
| master tree | `cb604d5d87f5c40b8032c7413e8740f0f62505e6` | 기존 Git 담당 publication/CI 증거의 고정 tree |
| master orchestrator blob | `cbbac082a7d3ae8e16efb7236595e42a2d738cc1f86a2e5e235f7fa0f61e81d3` | 원본430472/master745ef652의 LF 파일 SHA256. 현재 working 파일의 줄바꿈 정규화 SHA도 일치 |
| working 원시 파일 | `0d488e9b7d998a7bc3522c3f9c69493cf7d933170a1409d354940300e7b5a669` | CRLF를 포함하는 파일 bytes SHA256. LF master hash와 별도이며 미반영 변경의 증거로 사용하지 않음 |

[PR8](https://github.com/binkim00/life-infra-map/pull/8)과 [master push CI38349851893](https://github.com/binkim00/life-infra-map/actions/runs/38349851893)의 기존 고정 증거를 재사용했다. run event=push/head_sha=745ef652/completed/success, Django·Spring·웹·앱 네 job 모두 동일 head_sha/success를 저장 JSON으로 대조했다. 최신 CI를 새로 실행하거나 원격 refs를 갱신하지 않았다. CI는 일반 Django(config.test_settings), Spring test, 웹 test/build, 앱 TypeScript/lint/Node 검사 범위이며 v6 전용 package·실제 PostgreSQL 성능·실기기·운영 배포를 검사한 것이 아니다.

master의 통합 파일은 v6의 단독 운영 base와 다르다. v6 전체 파일을 master 위에 덮는 배포·Git 통합은 승인/수행하지 않았으며, 이를 완료 항목이나 자동 후속 작업으로 해석하면 안 된다.

## 12개 기준선·개선·조건 위반·rollback 연결

1. [운영 기준선/기능 분리](SEARCH_PIPELINE_RELEASE_REVIEW_2026-10-13.md): 고정 부산/서울×6조건, 카페5km·DB30/Kakao45·최종5. 당시 운영 source/flags/필수조건 위반0 및 원본 [12개 baseline](../runtime/search-pipeline-baseline-20261013.json). 자연어/공개 HTTP/실기기 검사는 별도다.
2. [두 항목 선별·rollback](SEARCH_PACKAGE_A_VALIDATION_2026-10-13.md), [실패 SQL 보완](SEARCH_PACKAGE_A_REVALIDATION_2026-10-13.md): 원시 근거 후보 추가와 gate 기반 reranker 비활성 fallback. 초기 timeout/누락은 후속 검증으로 대체했으며 실패 표본을 성공에 섞지 않았다.
3. [상세 통합 검증](SEARCH_HYDRATION_REPEAT_REVIEW_2026-10-13.md), [최종 v6 검증](SEARCH_PREPARED_EVIDENCE_REVIEW_2026-10-13.md): 관련90+준비 문맥3=고유93 회귀, AST/compile/정·역 patch/manifest 대조. 기존 v5와 v6의 동일12개×5회60쌍에서 실패/최종 identity순서·품질·candidate profile 불일치/필수조건 위반0. 중앙값508.39→244.30ms, 단발최대4,816.21ms는 남았다. [반복 집계](../runtime/search-package-a-v6-20261013/repeat-summary.json).
4. [서울 개별 SQL 진단](SEARCH_SEOUL_SQL_TAIL_REVIEW_2026-10-13.md): 후보 선택 heap I/O 증거 확인. v7 결과 회귀/v8 비용 회귀로 제외. 과거4.82초의 정확한 개별 wait를 소급 확정하거나 해결했다고 선언하지 않는다.
5. [PG17 초기 인덱스 검사](SEARCH_SEOUL_INDEX_ISOLATED_REVIEW_2026-10-13.md), [PG16.4 최종 실험](SEARCH_SEOUL_PG164_VISIBILITY_REVIEW_2026-10-13.md): 장소1,257,991·Tag863,623·Evidence291,067 합성 규모, 운영 nearest180의 희소/미확인/만료 근거 분포를 반영. 실제 운영 장소/근거 연결·OS·저장장치·HTTP의 복제는 아니다.
6. [PG16.4 5상태 집계](../runtime/search-index-pg164-20261013/summary.json): 12조건×5회×5상태=300쌍/600평가. 오류·identity/순서·품질/profile 불일치·필수조건 위반0. 근거 없는 결과는0개로 유지. 자동회복후 Heap Fetches0·선택5.035→3.310ms지만 서울 전체100.705→104.380ms(+3.65%),p95145.09→183.76ms로 관측상 회귀. 전체 지연의 일관된 개선은 미입증이므로 후보 채택을 보류하는 것으로 실험을 끝낸다. 순차 중지/재시작을 포함한 자동 회복 시간을 운영 SLA로 해석하지 않는다.

[v6 manifest](../runtime/search-package-a-v6-20261013/manifest.json), [v6 patch](../runtime/search-package-a-v6-20261013/change.patch), [rollback 원본](../runtime/search-package-a-v6-20261013/rollback/backend/recommendations/services/ai_search_orchestrator.py), [archive](../runtime/search-package-a-v6-20261013/search-package-a.tar.gz) hash를 이번 종료 확인에서 대조했다. 실제 배포·rollback 실행은 하지 않았다. runtime의 파일은 로컬 검토 자료이며 Git 반출 대상이 아니다.

## 종료 점검과 정말 남은 일

- 기존 검증을 재실행하지 않고 유효 요약·고정 manifest·CI metadata·Git blob/조상·새 운영 source hash만 읽었다. 두 격리 클러스터의 postmaster.pid 부재도 확인했다. 새 성능 실험/서비스 실행/추가 source 수정 없음.
- 새 v6의 운영 적용·실제 환경에서4.82초 해소는 **완료하지 않았으며 이번 종료 목표에서 제외**한다. 필수 잔여 검색 구현/검사 없음. 앞으로 별도 성능 작업을 요청하면 이 결과와 운영 환경 차이를 출발점으로 삼는다.
- Git 담당에게 넘길 잔여는 이 종료 보고서와 담당 문서의 보존/반영 여부 결정뿐이다. docs 통합·commit/push/PR/HEAD/index 조작은 본 담당이 수행하지 않는다.

## 최종 파일 목록·수정 종료

이번 최종화에서 수정/생성한 파일은 정확히2개:

- `docs/SEARCH_FINAL_CLOSEOUT_2026-10-14.md` — 이 최종 보고서.
- `docs/CODEX_STATE.md` — 검색 담당 종료 부분만 추가. 다른 담당 부분 유지.

이전 담당 문서8개는 위 링크대로 보존하고 이번에는 수정하지 않았다. 검색 관련 runtime private package/측정파일은 로컬 보존·Git 제외한다. `.env`/APK/DB/raw log·타 담당 source·문서는 Git 후보에 포함하라고 요청하지 않는다.

**수정 종료:** 이 보고서 및 state 기록 후 본 검색 담당은 추가 파일 수정 없이 완료 요약을 승인된 부모 채팅에 전달한다. Git 담당이 이2파일과 이전 검색 문서를 검토할 수 있는 최종 상태다. 과거 보고서의 “다음 실험/운영 인덱스 계획”은 이 종료 결정으로 대체한다.

운영 읽기 전용 확인: SSM `964ee43f-0e7f-4b02-bb03-5af9b0641391`, 2026-10-14, Success/response0, orchestrator SHA256 cc265e79…와 위 full SHA 일치.
