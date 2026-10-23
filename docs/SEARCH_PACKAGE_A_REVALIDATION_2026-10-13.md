# 검색 패키지 A 조회 개선·10개 비용·12개 결과 재검증 — 2026-10-13

> 최신 후속: [상세·근거 비용과5회 반복 측정](SEARCH_HYDRATION_REPEAT_REVIEW_2026-10-13.md). 최종 v5는 SQL수 중앙값13→10회,60쌍의 결과/근거 프로필 불일치0·조건 위반0. 그러나 전체시간509→535ms와 서울4종20% 이상 증가로 운영 성능 승인/배포 보류. 느려진 v4 프로필 대체는 제외했다.

## 판단

**추가 근거 조회 개선과 재검증 완료.** 최종 v3는 추가 조회 비용10종 모두 완료, EXPLAIN SQL 실행 합계 0.780~52.240ms다. 부산·서울12개 최종 결과 비교도 완료했다. 활성 필수조건을 가진10개 검색의 확인 결과 합계는0→35건(검색별 합계, 고유 장소35곳이라는 의미 아님), 응답 필드의 필수조건 위반0이다. 조건 없는 부산/서울 카페 검색은5건·identity 집합을 유지했고 서울 혼자+장기체류는0건을 유지했다.

관련 격리90개 검사 및 패키지 범위/적용/무결성 확인이 통과했다. 다만 전체 평가 지연은 일부 사례에서 늘어 **운영 지연 수용 기준 통과 또는 운영 배포 완료로 판단하지 않는다.** 서비스/공유 데이터/설정/키/마이그레이션/checkout/index/remote는 변경하지 않았다.

## 최종 패키지와 변경

[최종 v3 패키지](../runtime/search-package-a-v3-20261013/search-package-a.tar.gz), [manifest](../runtime/search-package-a-v3-20261013/manifest.json), [변경 diff](../runtime/search-package-a-v3-20261013/change.patch), [후보 source](../runtime/search-package-a-v3-20261013/candidate/backend/recommendations/services/ai_search_orchestrator.py).

- 운영 base/rollback SHA: `cc265e7968bfc8e1d2bfb689acd1ed257fc2c9095335ca8eaf005d0e1ad1972d`
- 최종 후보 SHA: `9d940771ce19b48f70b185ba2f1302f775a013da3f369fba49dc0b3cf815753f`
- archive SHA: `ac15f373eebd3d101088a96e59a029490045afb504a8f741b442b8a6ad162fcd`
- 공유 orchestrator SHA는 이전 `0d488e9b7d998a7bc3522c3f9c69493cf7d933170a1409d354940300e7b5a669` 유지. 실제 공유 검색 source에 이 패키지를 적용하지 않았다.
- 패키지 대상1파일, 기능2종(원시 유효 근거 후보 추가, 비활성 reranker의 필수조건 후보 fallback). 추가/변경 함수4개와 기존 모델 import만 포함한다. config/service module/migration/UI/수집/AI 공급자/trace/identity 변경은 포함하지 않는다.
- 이전 패키지와 실험 v2는 보존했고 최종 v3를 별도 경로로 만들었다.

기존 GROUP BY 조합 조회는 장소·태그·review/expiry join을 한 SQL로 묶었다. 실험 v2의 태그별 Exists 방식도 PostgreSQL이 큰 bounded Place 집합을 반복 조회하는 plan을 택해 서울 조용함 단일 조건에서3초 statement timeout이 발생했다. 최종 v3는 태그 ID를 먼저 읽고, **태그별 유효 양성 Evidence 장소 집합을 DB에서 순서대로 구한 뒤 교집합을 materialize**한다. 다음 태그 조회는 앞선 교집합으로 좁히며 빈 집합이면 중단한다. 마지막에 교집합 장소 좌표만 읽어 정확한 haversine 거리와 ID로 정렬한다.

추가 조회에서 review 없음 또는 approved, 만료 없음 또는 미래, polarity positive, 업종/좌표 bounds를 유지했다. 존재하지 않는 태그/필수조건 없음은 빈 추가 후보다. raw Evidence 발견은 confirmed 사실이 아니며 기존 hard gate/최종 결과 정책이 충돌·UNKNOWN·부분 충족을 다시 제외한다. 후보 축약 후 추가 근거 장소가 소실되지 않도록 유지하며 추가 조회 한도 max(limit,10)를 유지한다.

후속 fallback은 활성 필수조건이 있을 때만 grounded internal Evidence 경로를 적용한다. 조건 없는 검색의 순위를 바꾸지 않도록 범위를 좁혔다. AI 가중치·공급자 기능·조건 완화 정책은 바꾸지 않았다.

## 검증과 오류 정정

[격리 검사](../runtime/search-package-a-v3-20261013/isolated/backend/recommendations/test_package_a.py): 부산/서울×6조건, 후보 창 밖 장소, 비활성 reranker 보존, 만료·부분·충돌 배제, pending/approved_limited/rejected/research/approved 구분, 미등록 태그를 포함한 **90 tests / failures0 / errors0**, system check0 issues. 12개 subcase는90개에 포함되므로 합산하지 않는다.

최종 source compile, AST 함수 변경 범위, 제외 기능 검사, LF 정규화 원본에 patch apply check, archive 안의 후보/rollback hash 대조 통과. 격리 환경은 SQLite이며 운영 이미지 전체 dependency 검증은 아니다. 서버에서는 동일 base hash를 확인한 뒤 candidate를 메모리에만 생성했고 운영 PostgreSQL 실제 query와 결과를 검증했다.

실험 v2 평가의 `_condition_supported` 호출 인자가 뒤바뀌어, 필수조건 반환을 모두 위반으로 잘못 집계했다. 실제 signature `(condition, values)`에 맞춰 필수조건과 반환 `matched_conditions`를 대조하도록 고치고 v3에서 재측정했다. v2의 위반 수는 무효이며 v3의0건이 최신 관측이다. 원문 장소/주소/인용문이나 provider 키는 기록하지 않았다.

## 같은10개 추가 조회 비용

서버는 PostgreSQL REPEATABLE READ READ ONLY 트랜잭션, 일반 SQL5초/EXPLAIN3초 statement timeout, lock timeout1초, 실패 savepoint/rollback을 사용했다. 임시 process의 설정만 사용했으며 운영 DB 설정 변경이 아니다. AI reranker·AI Web Search 비활성 여부를 확인하고 바꾸지 않았다.

입력 query/primary query=카페, 카테고리cafe, 반경5km, DB기본30/Kakao45/최종5, 부산 (35.1796,129.0756), 서울 (37.5665,126.9780), 필수조건6종은 이전 고정 protocol을 유지했다. 부산1·서울1은 추가 query가 없는0비용 경로다.

| 시나리오 | 추가 SQL수 | EXPLAIN 실행ms 합계 | 결과 |
| --- | ---: | ---: | --- |
| 부산-2 | 3 | 52.240 | 완료 |
| 부산-3 | 3 | 15.218 | 완료 |
| 부산-4 | 4 | 26.468 | 완료 |
| 부산-5 | 5 | 19.002 | 완료 |
| 부산-6 | 4 | 0.884 | 완료 |
| 서울-2 | 3 | 22.511 | 완료 |
| 서울-3 | 3 | 2.685 | 완료 |
| 서울-4 | 4 | 20.800 | 완료 |
| 서울-5 | 5 | 44.711 | 완료 |
| 서울-6 | 3 | 0.780 | 완료 |

합계는 태그 ID·태그별 Evidence 집합·좌표 query의 **Execution Time**이며 planning/Python/첫 실행시간을 포함하지 않는다. 최종 helper를 실행해 SQL을 얻은 뒤 EXPLAIN하므로 warm cache 영향이 있다. 이전1회 표본 47.879~2,441.586ms와 기계적으로 나눠 개선율을 주장하지 않는다. cold-cache/동시 요청 부하/p95는 미측정이다. 반환 행이 적어도 전 태그의 유효 Evidence 집합을 읽는 비용이 발생하므로 넓은 지역·많은 조건으로 무제한 확장 가능한 증거는 아니다.

지난 서울4 실패 query를 같은3초 제한에서 다시 평가한 값은 v2 실험933.457ms, 최종 회차1,301.499ms로 완료됐다. 과거 실패 당시 SQLSTATE가 없어 원인을 소급 확정할 수 없다. 새로 재현한 v2 서울2 실패는 SQLSTATE57014/statement_timeout으로 원인을 분리했다. 최종10종에는 이 실패가 없다. index/schema/statistics/서비스 재시작으로 해결한 것이 아니다.

## 12개 실제 전후 결과

운영 base 코드와 메모리 candidate가 같은 트랜잭션의 DB snapshot을 읽고 도시당 한 Kakao snapshot을 공유했다. 양쪽 retrieval의 추가 후보 변화는 의도된 차이다. 각각 수집한 후보를 최종 평가에 고정 주입하고 query repair는 통제상 생략했다. 자연어 planner를 고정 frame으로 우회한 backend 파이프라인 비교이며 공개 HTTP/실사용 E2E 또는 live AI 평가가 아니다.

| 시나리오 | gate 기존→후보 | 최종 기존→후보 | 후보 조건위반 | 서버 평가ms 기존 / 후보 |
| --- | ---: | ---: | ---: | ---: |
| 부산-1 | 57→57 | 5→5 | 0 | 1043.3 / 720.3 |
| 부산-2 | 9→31 | 0→5 | 0 | 840.8 / 1198.9 |
| 부산-3 | 13→24 | 0→5 | 0 | 719.1 / 1333.1 |
| 부산-4 | 4→10 | 0→5 | 0 | 698.0 / 672.2 |
| 부산-5 | 4→6 | 0→5 | 0 | 863.9 / 1204.6 |
| 부산-6 | 0→3 | 0→3 | 0 | 826.7 / 605.1 |
| 서울-1* | 60→60 | 5→5 | 0 | 796.0 / 675.9 |
| 서울-2 | 0→17 | 0→5 | 0 | 442.2 / 1682.2 |
| 서울-3 | 0→10 | 0→5 | 0 | 490.6 / 1340.8 |
| 서울-4 | 0→1 | 0→1 | 0 | 563.9 / 642.4 |
| 서울-5 | 0→1 | 0→1 | 0 | 633.0 / 856.7 |
| 서울-6 | 0→0 | 0→0 | 0 | 455.6 / 650.6 |

*서울1은 첫 회차 **기존 코드 retrieval의 첫 SQL**이5초 제한에 걸렸다(SQLSTATE57014). 이 실패는 [첫 회차 집계](../runtime/search-package-a-v3-20261013/revalidation-first.json)에 보존했다. 해당 한 사례만 새 REPEATABLE READ snapshot에서 재실행해 양쪽5건·같은 identity 집합·위반0을 확인했다. 전체12개가 단일 시점에 연속 성공한 회차라고 표현하지 않는다.

[최종 집계](../runtime/search-package-a-v3-20261013/revalidation-final.json), [서울1 표적 재검사](../runtime/search-package-a-v3-20261013/revalidation-retry.json), [읽기 전용 재검증 코드](../runtime/search-package-a-v3-20261013/revalidate.py).

필수조건 행은 부산 조용함/콘센트/2조건/3조건이 각5건, 혼자+장기체류3건; 서울 조용함/콘센트 각5건,2조건/3조건 각1건,혼자+장기체류0건이다. 반환의 hard_gate_violations·all_conditions_met·모든 필수조건의 matched_conditions를 검사했다. 사람이 현실 장소 속성/false identity를 감사한 정밀도나 독립 출처 승인 성과가 아니다.

두 조건 없는 검색은 identity 소실0/새 identity0을 확인했다. 조건 검색의 추가 확인 반환35건은 **검색별 Top5 추가 반환 합계**이며 고유 장소/AI web 순증으로 해석하지 않는다. 필수조건 후보 부족을 임의 UNKNOWN 결과로 채우지 않았다.

이 표의 시간은 DB retrieval부터 최종 평가까지이며, 공통 Kakao 최초 네트워크·HTTP·intent 해석을 포함하지 않는다. 후보가 늘어 hydration/근거 프로필 조회도 늘었으므로 추가 SQL만 빨라도 전체 지연은 늘 수 있다. 예: 부산 콘센트719.12→1,333.10ms, 서울 조용함442.18→1,682.15ms. 한 번씩의 순차 측정과 cache/IO/동시 작업 변동이 섞여 있으므로 전체20% 수용 기준을 통과했다고 선언하지 않는다. 기존 code 자체의 first-query timeout도 별도 위험이다.

## 완료와 다음 단계

완료: 비용이 큰 집계/Exists 조회를 per-tag 집합 교집합으로 교체, 실패 SQLSTATE 구분, 최종10종 비용 성공,12개 결과 비교(1건 표적 재검사 포함), 필수조건 위반0·범위 보존 확인,90개 회귀, 최종 패키지/rollback/manifest/diff 무결성 확인.

남은 제한은 전체 retrieval hydration 지연·첫 조회 변동·동시 부하·반복 latency 표본과 운영 이미지 검사다. 실제 배포는 별도 승인 단계이며 현재는 성능 승인 보류다.

**다음 한 가지 행동:** 추가 후보 hydration·근거 프로필 단계의 비용을 분리해 개선하고 같은12개를 교차 순서로5회씩 측정해 전체 지연 수용 여부를 판단한다.
