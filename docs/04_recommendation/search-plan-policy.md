# SearchPlan 정책

## 1. 문서 목적

이 문서는 통합 지도 검색에서 사용자 자연어를 실행 가능한 검색 계획으로 바꾸는 기준을 정의한다.

현재 구현은 프론트엔드 `Homeview.vue`의 helper를 중심으로 SearchPlan을 만든다. 향후에는 같은 구조를 백엔드 SearchPlan API로 이전하는 것을 검토한다.

중요한 원칙은 특정 예시별 `if`를 계속 추가하는 것이 아니라, 모든 자연어 검색을 공통적으로 아래 구조로 분해하는 것이다.

```text
location + target + conditions + fallbackTargets + resultPolicy
```

---

## 2. 현재 구현된 SearchPlan 필드

현재 프론트 SearchPlan은 다음 필드를 중심으로 동작한다.

| 필드 | 상태 | 설명 |
|---|---|---|
| `originalQuery` | 구현됨 | 사용자가 입력한 원문 |
| `normalizedQuery` | 구현됨 | 공백 정리와 오타 보정을 거친 검색어 |
| `correctionApplied` | 구현됨 | 검색어 보정 여부 |
| `correctionReason` | 구현됨 | 적용된 보정 사유 |
| `searchMode` | 구현됨 | `current_context`, `around_location`, `region_search` 등 |
| `locationQuery` | 구현됨 | 지역 검색에서 기준 지역 |
| `baseLocationQuery` | 구현됨 | 기준 장소 검색어 |
| `targetQuery` | 구현됨 | 실제 검색 대상/조건 문장 |
| `targetType` | 구현됨 | `category`, `abstract`, `unknown` 중심 |
| `categoryHint` | 구현됨 | 카페, 주차장, 화장실 등 카테고리 힌트 |
| `categoryKeyword` | 구현됨 | 카카오 검색에 사용할 대표 키워드 |
| `recommendationIntent` | 구현됨 | `work_cafe`, `waiting_place`, `walk_healing`, `smoking_area` |
| `preferredTags` | 구현됨 | 추천 점수에 우선 반영할 태그 |
| `negativeTags` | 구현됨 | 추천에서 피해야 할 태그 |
| `kakaoKeywordCandidates` | 구현됨 | 카카오 검색 후보 키워드 |
| `confidence` | 구현됨 | 파싱 확신도 |
| `fallbackReason` | 구현됨 | 추상 표현 fallback 설명 |

현재 SearchPlan은 규칙 기반이며, AI가 아래 전체 구조를 JSON으로 반환하는 방식은 아직 구현되지 않았다.

---

## 3. 검색 모드

| searchMode | 상태 | 설명 |
|---|---|---|
| `current_context` | 구현됨 | 현재 위치를 먼저 시도하고 실패하면 지도 중심 기준으로 검색 |
| `around_location` | 구현됨 | `서면역 근처 카페`처럼 기준 장소를 먼저 확정한 뒤 주변 검색 |
| `region_search` | 구현됨 | `광주 카페`, `제주에서 산책하기 좋은 곳`처럼 지역 포함 검색 |
| `simple_keyword` | 구현됨 | 위치/추천 조건이 없는 일반 키워드 검색 |
| `recommendation_query` | 구현됨 | 추천 의도가 감지된 자연어 검색 |

현재 지도에서 재검색 버튼을 누르면 `current_context` 흐름으로 처리하되, 현재 지도 화면/중심을 기준으로 검색한다.

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

이 구조는 아직 전체 구현 완료 상태가 아니다. 현재는 `targetQuery`, `recommendationIntent`, `preferredTags`, `kakaoKeywordCandidates` 중심의 1차 구현이며, `conditions`, `fallbackTargets`, `resultPolicy`는 향후 개선 예정이다.

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

현재 구현은 장소/지역이 명시되지 않은 검색에서 현재 위치를 먼저 요청하고, 권한 거부나 실패 시 지도 중심으로 fallback한다.

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

현재 구현은 conditions를 독립 배열로 완전히 분리하지 않고, `recommendationIntent`와 `preferredTags`로 일부 표현한다. 독립 conditions 구조는 개선 예정이다.

---

## 8. fallbackTargets

`fallbackTargets`는 조건을 만족하는 target이 없거나 조건 확인이 어려울 때 보여줄 보조 결과다.

예:

| 입력 | target | condition | fallbackTarget |
|---|---|---|---|
| 흡연 가능한 맥도날드 | 맥도날드 | 흡연 가능 | 흡연구역 |
| 주차 가능한 해수욕장 | 해수욕장 | 주차 가능 | 주차장 |

fallbackTargets는 target 결과를 대체하지 않는다. 별도 그룹으로 표시해야 한다.

현재 구현은 fallbackTargets 그룹 표시가 아직 없다. 일부 검색에서는 추천 의도에 맞는 카카오 후보 키워드를 함께 검색하지만, target 보존/조건 fallback 그룹화는 개선 예정이다.

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

현재 화면은 `DB추천`, `카카오+DB`, `카카오` sourceLabel과 추천 정보 표시를 지원한다. 조건 충돌 안내와 fallback 그룹 UI는 개선 예정이다.

---

## 10. AI SearchPlan JSON 개선 예정

AI 파서는 실제 장소명, 주소, 좌표, 운영 여부, 시설 보유 여부를 생성하지 않는다.

향후 AI가 SearchPlan을 만들 때 반환해야 할 JSON은 다음 방향으로 제한한다.

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

- “흡연 가능한 맥도날드”처럼 조건과 target이 충돌할 수 있는 검색에서 target을 보존하는 처리
- “콘센트 있는 맥도날드”처럼 조건 확인이 어려운 결과에 “확인되지 않음”을 표시하는 처리
- “주차 가능한 해수욕장”처럼 target과 fallbackTarget을 별도 그룹으로 나누는 처리

### 향후 고도화

- 식당/음식/상품 키워드 처리
  - 근처 맛집
  - 혼밥하기 좋은 식당
  - 소금빵 맛집
  - 음식/상품 키워드를 위치로 오인하지 않는 처리
- SearchPlan 백엔드 API화
- AI SearchPlan JSON 생성
- 사용자 입력과 Tag/Category 설명 간 임베딩 기반 의미 매칭
- 하드코딩 키워드 매핑 축소
