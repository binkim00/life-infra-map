# 검색 수정 A 선별 패키지와 격리·PostgreSQL 검증 — 2026-10-13

> 최신 후속: [조회 개선·비용10종·결과12개 재검증](SEARCH_PACKAGE_A_REVALIDATION_2026-10-13.md). 최종 v3 추가 SQL10종 모두 완료(0.780~52.240ms),90개 회귀 통과, 조건 검색 확인 결과 합계0→35·위반0. 서울1 기존 코드 timeout은 한 건만 재검사해 완료했다. 아래 기록은 이전 패키지의 과거 증거이며, 최종 꾸러미는 v3 경로다. 전체 hydration/지연 승인은 여전히 보류다.

## 결과

**두 기능만 선별한 패키지 작성과 격리 회귀는 완료. 운영 제한 배포는 보류.** 추가 조회 비용 10종 중 9종 실측, 1종 OperationalError다. 완료된 조회도 47.879~2,441.586ms여서 비용 수용 기준을 통과했다고 볼 수 없다. 운영에 적용하거나 서비스·공유 설정·데이터·마이그레이션을 변경하지 않았다.

## 패키지와 범위

[선별 패키지](../runtime/search-package-a-20261013/search-package-a.tar.gz), [manifest](../runtime/search-package-a-20261013/manifest.json), [검토 diff](../runtime/search-package-a-20261013/change.patch), [후보 파일](../runtime/search-package-a-20261013/candidate/backend/recommendations/services/ai_search_orchestrator.py).

- archive SHA-256: `b9258ee44df995810abf6b92b11554711445259543a9e94c37bd65f7e5c62ec4`
- 확인한 운영/rollback 파일 SHA-256: `cc265e7968bfc8e1d2bfb689acd1ed257fc2c9095335ca8eaf005d0e1ad1972d`
- 후보 파일 SHA-256: `aedf971cfd1edb5ccb8c13888238eee1951b88f28def1914097519f0da67e353`
- 적용 대상은 `backend/recommendations/services/ai_search_orchestrator.py` 하나다. 꾸러미에는 candidate·원본 rollback·diff·manifest만 넣었다. 자동 적용 명령은 없다.
- 기능 1: 모든 필수 태그의 유효 양성 Evidence 조합 장소를 첫 거리 후보 창 밖에서도 조회하고 후보 축약 뒤에도 gate까지 보존.
- 기능 2: reranker 비활성/실패 시 internal Place·현재 gate·유효 Evidence가 있는 후보를 기존 필수조건 정책으로 다시 확인해 fallback 보존.
- 필요한 기존 모델/라이브러리 import는 Count·timezone·PlaceTagEvidence뿐이다. 새 service module/config/기능플래그/migration/UI/수집 변경은 0개다. identity·독립성 aggregation·trace/metrics·AI Web Search 파일럿·ranking 가중치 변경을 넣지 않았다.
- AST 기준 추가/변경 함수는 `_evidenced_required_place_ids`, `collect_db_candidates`, `_grounded_internal_fallback`, `_run_ai_search` 네 개다. 기능 2종이지 물리적 diff hunk 2개라는 의미는 아니다.

운영 hash와 intent/gate/Kakao dependency hash는 작업 시작 시 직접 재확인했고 이전 조사와 동일했다. 작업 중 공유 orchestrator는 수정하지 않았다. 확인한 공유 파일 hash `0d488e9b7d998a7bc3522c3f9c69493cf7d933170a1409d354940300e7b5a669`도 이전과 일치한다. checkout/index/commit/push는 변경하지 않았다.

## 격리 회귀와 추가 결함

개인 실행 폴더에 Python source만 복사하고 환경 파일·DB·비밀값은 제외했다. 후보 orchestrator와 확인된 배포 snapshot intent/gate/Kakao를 사용하고 SQLite in-memory DB에서 검사했다. 다른 dependency 전체가 운영과 byte 단위 일치하는 환경은 아니므로 운영 이미지 전체 회귀로 표현하지 않는다.

관련 검사 **89 tests, failures 0, errors 0**, Django system check 0 issues. 이 89개 안에 부산·서울 × 6조건의 12개 subcase가 들어 있다. 89+12개라고 합산하지 않는다.

[12개 격리 검사](../runtime/search-package-a-20261013/isolated/backend/recommendations/test_package_a.py)는 각 도시에 근거 없는 가까운 장소 210개와 조금 더 먼 유효 근거 장소를 만들었다. 조건 없는 검색은 기존 후보 identity 순서를 유지한다. 엄격 조건 10개는 원본 후보 창에서 누락된 유효 근거 장소가 후보 파일에서 검색되며, 필수조건에 필요한 Evidence가 없거나 만료/충돌이면 확인 결과를 채우지 않는다. reranker 실패·직접 외부 근거 없음·결정적 업종 경로 우회를 명시적으로 주입한 테스트에서 원본의 0건과 후보의 1건 보존을 비교했다. 이는 실패 경로의 합성 회귀이며 운영 개선 건수는 아니다.

초기 선별 구현에서는 새 근거 장소가 조회되어도 `_balance_candidate_pool_for_diversity`의 limit 축약에서 다시 사라졌다. 같은 기능 범위 내에서 이미 생성된 근거 후보를 balanced list에 중복 없이 추가해 gate로 전달하도록 수정했다. 조회 한도는 max(limit,10)이고 limit30 통제 검색의 DB 후보 상한은 기존30+추가최대30이다. 추가 장소가 TRUE라는 선언은 하지 않으며 만료/충돌/부분조건은 기존 gate와 최종 결과 정책이 판정한다.

PostgreSQL 조회는 기존 category retrieval의 방식과 맞춰 **bounded equirectangular 거리 정렬**로 선별했다. hydrate 뒤 기존 exact haversine 반경/gate를 유지한다. 초기 helper의 geography KNN 대신 범위 내 조합을 정렬하는 수정은 후보 추가 조회 항목에 포함했다. 한도 경계에서 정확한 거리순과 근사순이 다를 수 있어 엄격한 '정확히 가장 가까운 N개' 보장은 하지 않는다.

candidate compile·AST 범위 확인·제외 기능 문자열 검사·manifest hash 대조와 LF 정규화한 원본 파일에 `git apply --check`가 통과했다. rollback은 운영 확인 raw bytes를 그대로 보존했다. Windows diff의 CRLF로 인한 초기 적용 검사 실패는 LF patch 생성으로 수정했다. 테스트 실패나 도구 오류를 성공 기록에 포함하지 않았다.

## PostgreSQL 조회 비용

운영 PostgreSQL에 **READ ONLY 트랜잭션**, statement timeout3초·lock timeout1초·query별 savepoint·마지막 rollback을 적용했다. 운영 서비스 파일 대신 같은 hash의 후보 source를 메모리에만 생성하고 실제 ORM query를 `EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)`으로 평가했다. SQL 원문·params·장소 identity·근거 인용문·개인정보는 출력/저장하지 않았다.

기존 12개 frame/좌표/반경5km/한도30를 유지했다. 부산1·서울1은 필수조건이 없어 추가 Evidence query 자체가 없으므로 비용0 경로다. 나머지10종 결과는 다음과 같다. estimated cost는 PostgreSQL planner 단위이고 밀리초가 아니다.

| 시나리오 | 상태 | 실행ms | estimated cost | shared hit/read blocks |
| --- | --- | ---: | ---: | ---: |
| 부산-2 | measured | 2441.586 | 9001.54 | 17288/3980 |
| 부산-3 | measured | 258.03 | 9001.54 | 20047/252 |
| 부산-4 | measured | 1086.161 | 10408.93 | 23969/1971 |
| 부산-5 | measured | 175.005 | 10413.55 | 26385/159 |
| 부산-6 | measured | 106.385 | 10408.93 | 25374/31 |
| 서울-2 | measured | 693.963 | 15668.38 | 2788/1477 |
| 서울-3 | measured | 210.783 | 15668.38 | 1149/285 |
| 서울-4 | OperationalError | 미측정 | 미측정 | 미측정/미측정 |
| 서울-5 | measured | 173.632 | 26288.09 | 41589/4851 |
| 서울-6 | measured | 47.879 | 26287.09 | 45559/5 |

[익명 비용 집계](../runtime/search-package-a-20261013/postgresql-cost.json), [읽기 전용 비용 측정 코드](../runtime/search-package-a-20261013/measure-postgresql-cost.py).

9종은 계획·실행·buffer 비용을 확보했고 temp written blocks는 모두0이다. 서울4는 제한 범위 내 OperationalError를 기록했다. 당시 출력은 예외 클래스만 남겼으므로 **statement timeout/lock timeout/다른 DB 오류의 원인은 분리 확정할 수 없다**. 로그 원문이나 실패 SQL params를 재조회하지 않았다.

부산 query plan은 bounded 카페5,553개 뒤 Evidence index lookup이 반복되고, 서울은 조건에 따라 review/expiry 관련 bitmap 조합 또는 카페10,752개 범위의 병렬 plan을 사용했다. tag/review 조합의 estimated rows1과 actual aggregate100 등의 차이도 있다. 비용 차이는 cache/IO/동시 작업 영향과 계획 변화가 섞여 있으며 1회씩 측정한 값이다. 2.44초를 p95로 표현하지 않고, 기존 코드 대비 개선율도 계산하지 않는다. 통계 갱신·index·schema·planner 설정은 변경하지 않았다.

최초 운영 메모리 전후 평가 전체 실행은 5초 statement 제한으로 중단됐고 결과 JSON이 완성되지 않았다. 어느 단계에서 초과했는지는 제한된 오류 집계로 확정하지 못했다. 따라서 **운영 데이터의 12개 최종 결과 paired 비교는 미완료**이며 유효 전후 수치로 보고하지 않는다. 이번에 완료한 것은 격리 12개 회귀와 추가 SQL10종의 비용/실패 확인이다. 지난 baseline12개를 이번 후보의 실측 결과로 재사용하지 않는다.

## 배포 판단·남은 일

성능 수용 판정은 실패/보류다. 회귀 통과만으로 이 원시 Evidence query를 모든 검색에 켜는 배포를 승인 요청하지 않는다. 특히 조회 비용은 기본 검색 비용에 추가되며, 상위 limit로 인해 비용이 항상 limit에 비례해 작아지는 구조가 아니다. 별도 플래그 없는 변경이므로 이전 파일/이미지 복구가 필요하다.

남은 검증은 실패 query의 개인정보 없는 SQLSTATE/제한 종류와 plan 분리, 쿼리 구조 개선 후 같은10종 비용 비교, 최종 운영 메모리 전후12개 결과 비교다. 현재 source support에 대한 완전한 운영 dependency/이미지 검사도 배포 전 필요하다. AI 성과·provider latency·배포 성공은 주장하지 않는다.

**다음 한 가지 행동:** 서울4 실패와 반복 Evidence join의 비용을 익명 query plan·SQLSTATE로 분해해 쿼리를 개선하고 동일10종 비용 및 12개 최종 결과 비교를 다시 검증한다.
