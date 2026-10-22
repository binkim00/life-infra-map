# 검색 후보 상세·근거 조회 개선과 5회 반복 측정 — 2026-10-13

> 최신 후속: [v6 반복 근거 계산·서울 지연 검토](SEARCH_PREPARED_EVIDENCE_REVIEW_2026-10-13.md). 요청 내 공통 계산 재사용과 확인 태그 KNN 제거 후93개 회귀,60쌍 불일치/위반/실패0. 전체 median508.39→244.30ms·12개 median 모두 개선. 서울1 단발4.82초는 선택/상세 SQL에서 남았으므로 tail 해소/운영 배포 완료는 아니다.

## 결과와 결정

**후보 상세 조회 중복은 줄였지만 전체 검색 지연 개선은 입증하지 못했다. 운영 배포 보류.** 최종 v5는 v3에 비해 SQL수 중앙값13→10회(-23.1%), 장소 선택/상세 조회5→3회, 태그 조회3→2회로 줄었다. 그러나 전체 서버 평가 중앙값509.00→534.63ms(+5.0%), 서울4종의 사례별 중앙값은20% 이상 늘었다. 지연 수용 기준을 통과하지 못했다.

동일12개를 버전·도시·시나리오 교차 순서로5회씩 측정해 **60 paired cases / 120 evaluations**, 실패0, 후보 프로필·결과 품질·결과 identity 순서 불일치0, 필수조건 위반0을 확인했다. 기본 확인 결과 수/필수조건 정책은 유지됐으며 UNKNOWN·부분 충족 결과로 개수를 채우지 않았다. 이 작업은 로컬 패키지와 서버의 읽기 전용 임시 process 평가이며 배포/운영 설정/데이터/마이그레이션/키/checkout/index/remote 변경은 없다.

## 최종 수정과 제외한 실험

[최종 검토용 v5 패키지](../runtime/search-package-a-v5-20261013/search-package-a.tar.gz), [manifest](../runtime/search-package-a-v5-20261013/manifest.json), [검토 diff](../runtime/search-package-a-v5-20261013/change.patch). 운영 적용 승인용으로 확정한 패키지가 아니다.

- 후보 SHA `a53b6dbc42c49c3d65d0e165fbbe9d365999de28c92a5271664dd87b9cbc185e`
- archive SHA `d8c2a334c6685aae2275369017d8feeef675aa164d2732da1ffae01cf4e31191`
- 원본/복구 SHA `cc265e7968bfc8e1d2bfb689acd1ed257fc2c9095335ca8eaf005d0e1ad1972d`
- 비교 v3 SHA `9d940771ce19b48f70b185ba2f1302f775a013da3f369fba49dc0b3cf815753f`
- 공유 orchestrator는 이전 SHA `0d488e9b7d998a7bc3522c3f9c69493cf7d933170a1409d354940300e7b5a669` 유지.

v3에서는 초기 거리 후보의 상세/태그를 읽고, 추가 근거 장소의 상세/태그를 다시 읽었다. v5는 후보 identity 순서만 먼저 정한 뒤 두 집합을 합쳐 **상세 모델·기존 태그를 한 번에 hydrate**한다. 기존 태그 prefetch, raw/URL annotation, smoking 분기, history/verified/suggested 상태, Evidence 프로필 함수를 유지했다. SQL수 감소는 특히 추가 장소가 있는 조건 검색에서 관측됐다. 조건 없는 검색이나 추가0건 검색은 감소폭이 같지 않다.

초기 v4 실험에서는 태그 select_related와 lean/distinct 근거 프로필 조회도 시험했다. 60쌍 모두 프로필·결과가 같았지만, 프로필 wall 중앙값13.85→19.96ms, profile SQL1→2회로 늘었다. 이 변경은 **제외**했다. 최종 v5는 프로필 계산/태그 prefetch를 원래 구현으로 복원했으며 새 profile helper를 포함하지 않는다. 원래 계산과 동등한 값이라는 이유만으로 느린 구현을 성능 개선으로 채택하지 않았다.

패키지에는 기존 두 검색 기능(원시 근거 후보 추가와 필수조건 fallback) 및 그 상세 조회 통합만 있으며 단일 orchestrator 파일/변경 함수4개다. 수집·UI·identity·trace·AI 공급자·ranking 가중치·schema/index 변경은 없다. v3/v4 기록과 꾸러미도 보존했다.

## 검증

최종 v5 관련 격리 **90 tests 통과**, system check0 issues. 부산·서울12개 조건 조합, 후보 창 밖 유효 근거, 만료/부분/충돌, review 상태, 필수조건 없는 검색, 비활성 reranker fallback을 포함한다. v4 실험은 여기에 duplicate/negative/expiry/source count·historical tag·혼합업종/빈목록3개 검사를 추가해 고유93개를 확인했지만, 최종 패키지의 검사 수는90개로 구분한다.

AST 변경 범위, compile, 제외 기능 검사, LF 원본의 patch apply check, archive 후보/rollback hash 대조 통과. 초기 상세 지연 구현이 SQLite 경로만 stub으로 바꿔 조건 없는 결과를 비우는 회귀를 검사에서 발견했고, 모든 경로가 실제 상세 모델을 한 번에 읽도록 고친 뒤 재검사했다.

운영 평가 process는 확인된 base hash의 코드를 읽고 candidate를 메모리에 생성한다. 저장된 운영 파일은 교체하지 않았다. PostgreSQL REPEATABLE READ READ ONLY, statement timeout5초/lock timeout1초, 실패 savepoint 및 마지막 rollback을 사용했다. AI reranker/AI Web Search 비활성 상태를 확인했다.

## 반복 측정 방법과 범위

입력은 이전 protocol의 카페 query/카테고리cafe, 부산 (35.1796,129.0756), 서울 (37.5665,126.9780), 반경5km, DB기본30·Kakao45·Top5 및 조건6종이다. 도시당1개 Kakao snapshot을 공유하며 한 READ ONLY snapshot에서 같은 시나리오를5회 비교했다. 반복마다 도시/시나리오 순서를 뒤집고 버전 실행 순서를 교차했다. AI 자연어 planner와 query repair는 통제상 우회/생략했다.

단계별 SQL시간/횟수와 raw discovery·profile 함수 wall 시간을 수집했다. 장소 선택/상세 SQL에는 기본 검색·확인 태그 조회도 포함돼 있어 순수 상세 전송시간만 분리한 값은 아니다. SQL 실행 wrapper의 시간은 cursor 실행이며 모든 fetch/model 생성/Python 계산을 포함하지 않는다. wall=0으로 표시된 상세/태그 단계는 미계측이지 실제0ms가 아니다.

최초 상세 JSON 출력은 SSM 출력 한도로 잘려 **유효 반복 결과에서 제외**하고, 동일 측정을 압축 출력으로 다시 확보했다. 개인정보/원문/SQL params 없이 숫자·동일성 boolean만 기록했다. 이후 느린 프로필 실험을 제외하고 v5로 다시5회 측정했다. 서로 다른 회차의 v3 값을 섞어 개선율을 계산하지 않는다.

[최종120회 결과](../runtime/search-package-a-v5-20261013/repeat-results.json), [최종 요약](../runtime/search-package-a-v5-20261013/repeat-summary.json), [실행 코드](../runtime/search-package-a-v5-20261013/repeat-compressed.py). [제외한 v4 실험](../runtime/search-package-a-v4-20261013/repeat-summary.json)은 별도 회차다.

## 단계별 중앙값

| 지표 | v3 | v5 | 해석 |
| --- | ---: | ---: | --- |
| 전체 서버 평가 | 509.00ms | 534.63ms | +5.0%, 전체 개선 실패 |
| retrieval | 424.69ms | 427.02ms | 거의 동일, 개선 입증 못함 |
| 전체 SQL수 | 13회 | 10회 | 조회 중복 감소 |
| 장소 선택/상세 SQL수 | 5회 | 3회 | 초기·추가 집합 통합 |
| 장소 선택/상세 SQL시간 | 19.48ms | 18.67ms | 작은 차이, causal 개선율로 확정 안 함 |
| 태그 SQL수 | 3회 | 2회 | 한 번에 prefetch |
| 태그 SQL시간 | 9.33ms | 10.29ms | query 수 감소가 시간 감소로 바로 이어지지 않음 |
| profile SQL수 | 1회 | 1회 | 기존 계산 유지 |
| profile wall | 13.24ms | 14.79ms | 구현 동일, 변동 관측 |
| raw discovery wall | 36.18ms | 25.26ms | 구현 동일, cache/IO/동시 부하 영향 가능 |
| 전체 최대 | 2,901.21ms | 4,503.25ms | tail 위험 남음 |

동시 부하·IO·cache를 인위적으로 통제하거나 재시작/flush하지 않았다. 동일 구현 단계의 시간이 다르므로 버전 간 전부를 코드 변화의 인과 효과라고 해석하지 않는다. 5회 표본의 median/max이며 공개 HTTP·Kakao 최초 네트워크·intent 시간은 제외한다. 운영 서비스 p95나 cold-cache 성능을 입증하지 않는다.

## 12개 시나리오의 5회 중앙값

| 시나리오 | v3 ms | v5 ms | 변화 | 양쪽 최종 결과수 |
| --- | ---: | ---: | ---: | ---: |
| 부산-1 | 468.02 | 520.24 | +11.2% | 5 |
| 부산-2 | 571.72 | 510.72 | -10.7% | 5 |
| 부산-3 | 536.13 | 579.09 | +8% | 5 |
| 부산-4 | 489.07 | 486.99 | -0.4% | 5 |
| 부산-5 | 559.04 | 485.38 | -13.2% | 5 |
| 부산-6 | 520.72 | 451.57 | -13.3% | 3 |
| 서울-1 | 556.65 | 1003.37 | +80.3% | 5 |
| 서울-2 | 1374.82 | 663.87 | -51.7% | 5 |
| 서울-3 | 432.31 | 1049.36 | +142.7% | 5 |
| 서울-4 | 428.43 | 698.16 | +63% | 1 |
| 서울-5 | 464.11 | 755.60 | +62.8% | 1 |
| 서울-6 | 520.36 | 375.92 | -27.8% | 0 |

모든60쌍의 후보별 Evidence 프로필 dict와 최종 result quality/필수조건 판정/identity 순서가 일치했다. 두 버전 모두10개 엄격 조건 검색에서 한 회차35건(검색별 합계)을 유지하며 서울 혼자+장기체류0건이다. 사람이 장소 속성과 identity precision을 감사한 수치가 아니며 AI Web Search 기여로 해석하지 않는다.

서울1·3·4·5의 사례 median 증가가20% 기준을 넘었다. 다른 시나리오의 개선으로 상쇄해 전부 통과했다고 처리하지 않았다. **v5 운영 배포/성능 승인은 보류**, v4 프로필 실험은 제외다.

## 완료·남은 일·다음 행동

완료: 상세/태그 중복 조회 통합, 프로필 대체 실험의 동등성·비용 확인 후 제외, 최종90개 회귀, v3/v5의12개×5회 전후 측정, 실패/불일치/위반0 확인, query수 감소와 전체지연 한계 기록. 운영 적용은 실행하지 않았다.

남은 병목은 서버 wall 시간에서 SQL 외 비용과 서울 raw discovery/첫 선택 query의 지연 변동이다. SQL수를 더 줄이는 것만으로 전체 응답 개선을 보장할 수 없다.

**다음 한 가지 행동:** 장소별 근거 판정의 반복 계산과 서울 선택·raw discovery의 지연 변동을 분리해 개선한 뒤 동일12개 반복 측정으로 수용 기준을 재검증한다.
