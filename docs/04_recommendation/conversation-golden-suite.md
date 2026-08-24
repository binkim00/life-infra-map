# 대화형 검색 골든 평가셋

## 목적

`backend/recommendations/evaluation_cases/conversation_golden_30.json`은 대화형 장소 추천이
검색 문장 하나만 처리하는 수준을 넘어 이전 위치, 대상, 누적 조건, 제외 조건과 결과 참조를
유지하는지 검증하는 기준이다.

평가셋은 30개 대화와 59개 발화 단계로 구성한다. 주요 범위는 다음과 같다.

- 부모님·가족 식사
- 조용한 작업 카페
- 휴식·산책·우천 대피
- 화장실·약국·주차장·흡연구역
- 조건 추가·제외·거리 우선
- 이전 결과 비교·선택·제외
- 대화 초기화
- 문맥 없는 지시어, 범위 밖 요청과 차단 요청

## 실행

외부 AI와 웹 검색을 끈 결정적 기준선은 다음 명령으로 실행한다.

```powershell
$env:CONVERSATIONAL_SEARCH_AI_ENABLED='false'
$env:AI_RERANK_ENABLED='false'
$env:AI_WEB_SEARCH_ENABLED='false'
$env:SEMANTIC_RETRIEVAL_ENABLED='false'
$env:SEMANTIC_CANDIDATE_INJECTION_ENABLED='false'
$env:KAKAO_REST_API_KEY=''
python manage.py evaluate_ai_search `
  --case-file recommendations/evaluation_cases/conversation_golden_30.json `
  --no-log `
  --output conversation-golden-result.json
```

`evaluate_ai_search`는 각 단계의 기존 결과 품질 검사에 더해 다음 기대 상태를 검사한다.

- `expected_action`
- `expected_scenario`
- `expected_location_terms`
- `expected_conditions_all`
- `expected_exclusions_all`
- `expected_target_terms`
- `expected_sort_hint`

## 2026-08-23 로컬 기준선

- 대화: 30개
- 발화 단계: 59개
- 정상 판정: 12개
- 점검 필요: 47개
- `ai_unavailable`: 21개
- 검색 실행 후 결과 없음: 13개
- 기대한 후속 검색이 `ai_unavailable`: 11개
- 거리 우선 정렬 문맥 누락: 6개
- 후속 요청이 새 검색으로 처리됨: 6개
- 후속 요청이 불필요한 되묻기로 처리됨: 6개

이 수치는 로컬 DB와 외부 공급자 비활성 상태의 기준선이다. 서버 DB 기준선은 동일한 케이스를
읽기 전용으로 실행해 별도로 기록한다. 현재 가장 큰 로직 결함은 데이터 수보다 먼저,
후속 발화가 이전 검색 frame을 안정적으로 갱신하지 못한다는 점이다.

## 2026-08-23 서버 DB 기준선

- 실행 방식: PostgreSQL `default_transaction_read_only=on`, 외부 AI·웹·Kakao 비활성
- 발화 단계: 59개
- 정상 판정: 12개
- 점검 필요: 47개
- intent accuracy: 0.4068
- `ai_unavailable`: 22개
- 검색 실행 후 결과 없음: 13개
- hard violation rate: 0.0
- 평균 응답시간: 771.37ms
- p95 응답시간: 3279.74ms

로컬과 서버의 정상 판정 수가 같으므로 대화 실패의 우선 원인은 DB 선택이 아니라 후속 발화
상태 갱신이다. 데이터 측면에서는 작업 카페·산책·쇼핑 조합의 0건 결과를 별도 개선 대상으로
분류한다.

## 운영 원칙

- 원본 평가 JSON은 실행 환경의 임시 산출물로 관리하고 저장소에는 커밋하지 않는다.
- 평가셋의 기대값을 현재 구현에 맞춰 낮추지 않는다.
- 실패를 수정할 때 관련 발화만 통과시키지 말고 전체 59단계를 다시 실행한다.
- 서버 DB 평가에서는 DB 기본 트랜잭션을 읽기 전용으로 강제한다.

## 부산 출시 품질 세트

대화 상태 처리와 별도로 실제 추천 근거가 상위 결과에 존재하는지는
`backend/recommendations/evaluation_cases/busan_launch_quality_24.json`의 카페 12건,
식당 12건으로 매일 측정한다. 운영 서버의 `life-infra-map-quality-report.timer`는
증거 수집 이후 이 세트를 실행하고 `feature_query_hit_at_5_rate`와
`verified_feature_result_rate_at_5`를 포함한 출시 게이트를 JSON으로 남긴다.
