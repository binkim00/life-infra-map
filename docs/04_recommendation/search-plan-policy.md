# AI frame / SearchPlan 정책

## 1. 문서 목적

이 문서는 홈 AI 추천 검색에서 사용자 자연어를 실행 가능한 검색 frame으로 바꾸는 기준을 정의한다.

현재 구현은 백엔드 `/api/recommendations/ai-search/`의 AI-first 오케스트레이터를 중심으로 동작한다. 일반 지도 검색(`/map`, `/api/recommendations/map-search/`)은 AI 해석 없이 DB `Place`와 Kakao 키워드 결과를 그대로 조회하므로 이 문서의 자연어 추천 정책과 분리한다.

중요한 원칙은 특정 예시별 `if`를 계속 추가하는 것이 아니라, 모든 자연어 검색을 공통적으로 아래 구조로 분해하는 것이다.

```text
location + target + conditions + fallbackTargets + resultPolicy
```

---

## 2. 현재 구현된 AI frame 필드

현재 AI-first 추천 검색은 다음 frame 필드를 중심으로 동작한다.

| 필드 | 상태 | 설명 |
|---|---|---|
| `target_objects` | 구현됨 | 사용자가 찾는 대상 |
| `result_match_terms` | 구현됨 | 결과가 직접 맞아야 하는 핵심 표현 |
| `candidate_place_types` | 구현됨 | 후보로 허용할 장소 유형 |
| `constraints` | 구현됨 | 가까움, 도보, 실내/실외 등 조건 |
| `exclusions` | 구현됨 | 카페 제외, 주차장 제외, 웹 근거 제외 등 부정 조건 |
| `evidence` | 구현됨 | AI가 판단한 요청 근거 |
| `location_mode` | 구현됨 | `explicit`, `current_context`, `clarification_required` |
| `anchor_location` | 구현됨 | 명시 위치 기준 |
| `primary_search_queries` | 구현됨 | DB/Kakao 후보 수집용 검색어 |
| `ranking_policy` | 구현됨 | evidence first, urgent nearest 등 정렬 정책 |

현재 구현은 AI frame을 우선 사용하고, DB/Kakao/Web 후보는 backend collector와 unified evidence ranker/reranker를 거쳐 표시한다.

---

## 3. 위치 모드

| location mode | 상태 | 설명 |
|---|---|---|
| `current_context` | 구현됨 | 현재 좌표 또는 지도 중심 좌표 기준 |
| `explicit` | 구현됨 | `서면역 근처 카페`처럼 기준 장소를 먼저 좌표로 확정 |
| `clarification_required` | 구현됨 | 위치나 대상이 넓어 바로 검색하기 어려운 경우 |

`current_coordinates` 같은 내부 좌표 표식은 실제 장소명으로 지오코딩하지 않고 `current_context`로 정리한다.

---

## 4. 공통 SearchPlan 목표 구조

향후 SearchPlan은 아래 구조를 목표로 정리한다.

```json
{
  "originalQuery": "흡연 가능한 맥도날드",
  "normalizedQuery": "흡연 가능한 맥도날드",
  "location": {
    "mode": "current_location",
    "query": null,
    "explicit": false,
    "source": "current_context"
  },
  "target": {
    "raw": "맥도날드",
    "keyword": "맥도날드",
    "type": "brand",
    "categoryHint": "restaurant",
    "kakaoKeywords": ["맥도날드"]
  },
  "conditions": [
    {
      "key": "smoking_allowed",
      "label": "흡연 가능",
      "tags": ["흡연가능"],
      "verificationRequired": true
    }
  ],
  "fallbackTargets": [
    {
      "keyword": "흡연구역",
      "conditionKey": "smoking_allowed",
      "groupLabel": "주변 흡연 가능 장소"
    }
  ],
  "resultPolicy": {
    "primaryMustKeepTarget": true,
    "showFallbackSeparately": true,
    "doNotAssertUnverifiedCondition": true
  }
}
```

이 구조는 장기 목표다. 현재는 AI frame의 `target_objects`, `result_match_terms`, `candidate_place_types`, `constraints`, `exclusions`, `evidence`를 중심으로 구현되어 있으며, `conditions`, `fallbackTargets`, `resultPolicy`의 명시적 분리는 향후 개선 예정이다.

---

## 5. location

`location`은 어디를 기준으로 검색할지 나타낸다.

| mode | 설명 |
|---|---|
| `current_location` | 브라우저 현재 위치 기준 |
| `map_center` | 현재 위치를 가져오지 못했거나 지도 재검색 시 지도 중심 기준 |
| `base_place` | 특정 장소를 먼저 검색해 좌표를 확정 |
| `region` | 지역명 포함 키워드로 전체 검색 |
| `none` | 위치 기준이 필요 없는 검색 |

현재 구현은 장소/지역이 명시되지 않은 추천 검색에서 현재 좌표 또는 지도 중심 좌표를 사용한다. 좌표가 없고 기준 위치도 없으면 clarification을 요청한다.

---

## 6. target

`target`은 사용자가 실제로 찾는 대상이다.

예:

- 카페
- 식당
- 맥도날드
- 소금빵 맛집
- 화장실
- 주차장
- 공원
- 관광지
- 해수욕장
- 흡연구역

음식, 상품, 브랜드, 장소 카테고리는 target으로 처리한다. 음식/상품 키워드를 위치로 오인하지 않는 처리는 아직 개선 예정이다.

---

## 7. conditions

`conditions`는 target에 붙은 조건이다.

예:

- 흡연 가능
- 콘센트 있음
- 조용함
- 실내
- 혼밥
- 주차 가능
- 야경
- 산책 좋음
- 잠깐 쉴 수 있음

중요한 원칙:

- 조건은 target을 대체하지 않는다.
- “흡연 가능한 맥도날드”에서 target은 `맥도날드`, condition은 `흡연 가능`이다.
- 흡연 가능 조건이 있다고 target을 `흡연구역`으로 바꾸면 안 된다.
- 조건 만족 여부를 확인할 수 없으면 만족한다고 단정하지 않는다.

현재 구현은 conditions를 독립 배열로 완전히 분리하지 않고, AI frame의 `constraints`, `exclusions`, `result_match_terms`로 일부 표현한다. 독립 conditions 구조는 개선 예정이다.

---

## 8. fallbackTargets

`fallbackTargets`는 조건을 만족하는 target이 없거나 조건 확인이 어려울 때 보여줄 보조 결과다.

예:

| 입력 | target | condition | fallbackTarget |
|---|---|---|---|
| 흡연 가능한 맥도날드 | 맥도날드 | 흡연 가능 | 흡연구역 |
| 주차 가능한 해수욕장 | 해수욕장 | 주차 가능 | 주차장 |

fallbackTargets는 target 결과를 대체하지 않는다. 별도 그룹으로 표시해야 한다.

현재 구현은 fallbackTargets 그룹 표시가 아직 없다. 일부 검색에서는 백엔드 collector가 Kakao/Web 후보를 보강하지만, target 보존/조건 fallback 그룹화는 개선 예정이다.

---

## 9. resultPolicy

결과 표시 정책은 다음 원칙을 따른다.

- 조건을 모두 만족하는 target 결과가 있으면 우선 표시한다.
- 조건 만족 여부가 확인되지 않으면 “확인되지 않음”으로 안내한다.
- target 결과는 버리지 않는다.
- fallbackTargets는 별도 그룹으로 표시한다.
- 조건을 만족하는 target이 없으면 안내 문구를 표시한다.

안내 문구 예:

```text
입력한 조건을 모두 만족하는 장소는 확인되지 않았습니다.
대신 대상 장소와 조건 관련 장소를 함께 표시합니다.
```

현재 화면은 `DB추천`, `카카오 후보`, `웹 참고` 등 backend sourceLabel과 추천 정보를 표시한다. 추천 점수는 정렬용 내부 값으로만 사용하고, 사용자 화면에는 직접 노출하지 않는다. 조건 충돌 안내와 fallback 그룹 UI는 개선 예정이다.

---

## 10. AI frame JSON 개선 예정

AI 파서는 실제 장소명, 주소, 좌표, 운영 여부, 시설 보유 여부를 생성하지 않는다.

향후 AI frame을 더 명확히 확장할 때 반환해야 할 JSON은 다음 방향으로 제한한다.

```json
{
  "location": {
    "mode": "current_location | map_center | base_place | region | none",
    "query": null,
    "explicit": false
  },
  "target": {
    "raw": "맥도날드",
    "keyword": "맥도날드",
    "type": "brand | food | category | facility | place | abstract | unknown",
    "categoryHint": "restaurant",
    "kakaoKeywords": ["맥도날드"]
  },
  "conditions": [
    {
      "key": "smoking_allowed",
      "label": "흡연 가능",
      "tags": ["흡연가능"],
      "negativeTags": [],
      "verificationRequired": true
    }
  ],
  "fallbackTargets": [
    {
      "keyword": "흡연구역",
      "conditionKey": "smoking_allowed",
      "groupLabel": "주변 흡연 가능 장소"
    }
  ],
  "resultPolicy": {
    "primaryMustKeepTarget": true,
    "showFallbackSeparately": true,
    "doNotAssertUnverifiedCondition": true
  },
  "confidence": "high | medium | low"
}
```

---

## 11. 현재 남은 개선 항목

### 당장 검토 필요

- 쌀국수/맛집류에서 Kakao 후보가 충분히 남는지 확인
- 화장실류에서 “근처” 반경과 제외 조건이 과하게 넓거나 약하지 않은지 확인
- 흡연구역류에서 실내/실외 정책과 지역별 결과 편차 확인
- broad clarification 후 영화관/공연, 쇼핑/백화점, 바/술집 같은 선택지 품질 확인
- “주차장 빼줘”, “카페/디저트 제외”, “웹 근거 제외” 같은 부정 조건 품질 확인

### 향후 고도화

- 식당/음식/상품 키워드 처리
  - 근처 맛집
  - 혼밥하기 좋은 식당
  - 소금빵 맛집
  - 음식/상품 키워드를 위치로 오인하지 않는 처리
- AI frame을 `conditions`, `fallbackTargets`, `resultPolicy`까지 명시적으로 확장
- 사용자 입력과 Tag/Category 설명 간 임베딩 기반 의미 매칭
- 하드코딩 키워드 매핑 축소

---

## 12. Evidence-grounded Hybrid Ranking

AI reranker가 반환한 semantic score가 기존 점수를 덮어쓰지 않는다. 후보의 최종 점수는 다음
구성 요소를 설정 가능한 가중치로 합산한다.

- condition 0.20
- tag 0.10
- semantic 0.35
- distance 0.10
- evidence 0.10
- freshness 0.05
- reliability 0.10

가중치는 `AI_SEARCH_WEIGHT_*` 환경변수로 조정한다. 결과의 `score_breakdown`에는 각 구성 점수,
penalty, 최종 점수와 적용 가중치를 남긴다. `pre_ai_unmet_constraints`가 있는 후보는 AI가 include를
반환해도 `hard_condition_failed`로 제외된다. 사용자에게 보이는 추천 이유는 LLM의 자유 문장이
아니라 Candidate의 검증 태그, 일치 조건, Category, 거리로만 다시 구성해 Evidence에 없는
정성 주장을 차단한다.

## 13. Evaluation과 Semantic Retrieval 준비 상태

`evaluate_ai_search`는 case file에 `expected_action`, `expected_anchor_location`,
`relevance_labels`가 있을 때 Intent, Region, Recall@K, MRR, NDCG를 계산한다. 정답이 없으면
숫자를 만들지 않고 `NOT_MEASURED`로 기록한다. Hard violation, no-result, fallback, latency는
실행 결과만으로 측정한다.

`PlaceFeatureDocument`는 Place 이름, Category, 주소와 활성 positive Feature만 조합한다.
stale/rejected/needs_verification은 제외하고, candidate는 confidence 50 이상이면서 활성 positive
Evidence가 있을 때만 포함한다. 다음 명령은 외부 호출 없이 문서를 멱등 생성한다.

    python manage.py build_place_feature_documents --category cafe --limit 100 --dry-run
    python manage.py build_place_feature_documents --category cafe --limit 100

현재 PostgreSQL에는 PostGIS, pg_trgm, unaccent가 있지만 pgvector가 없고 로컬 Embedding Provider도
설정되지 않았다. 따라서 `SEMANTIC_RETRIEVAL_ENABLED=false`가 기본이며 실제 vector 검색이나 대량
embedding은 구현 완료로 간주하지 않는다. 가짜/random vector와 유료 API 대량 호출은 사용하지
않는다.
