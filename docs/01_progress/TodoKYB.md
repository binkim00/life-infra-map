# KYB 진행 상황 요약

## 1. 현재 프로젝트 방향

상황 기반 생활 장소 추천 지도 서비스는 단순 지도 검색이 아니라, 사용자의 위치와 상황에 맞는 생활 장소를 추천하고 추천 결과를 지도에서 확인하는 서비스입니다.

초기 추천은 머신러닝보다 규칙 기반으로 구현합니다.

```text
추천 기준 = 카테고리 + 태그 + 거리 + 최신성 + 신뢰도 + 확인 필요 감점
```

---

## 2. 현재 구현된 내용

### 2.1 태그 저장 원칙 정리

- `Place.category`만으로 알 수 있는 기본 태그는 `PlaceTag`에 저장하지 않음
- 추천/필터에 실제로 쓸 세부 속성 태그만 저장
- DB에는 source를 세분화해서 저장하고, 화면/API에서는 display_group으로 묶어서 출력
- 블로그/AI/키워드 기반 태그는 확정 정보가 아니라 후보 정보로 관리

---

### 2.2 통합 지도 검색 화면

- 추천 테스트 탭은 제거하고 지도 탭 중심으로 통합했습니다.
- 지도 탭에서 일반 장소 검색, AI/추천 검색, 지역 검색, 현재 지도 화면 재검색을 처리합니다.
- 빠른 상황 버튼을 지도 검색 영역에 배치했습니다.
  - 조용히 작업할 곳
  - 잠깐 쉴 곳
  - 산책/힐링
  - 흡연 가능한 곳
- 검색 중 지도 오버레이, 목록 스켈레톤, 단계별 로딩 문구를 표시합니다.
- 테스트용 현재 위치/기본 위치 선택 버튼은 유지되어 있으나 운영 전 제거 또는 정리할 수 있습니다.

---

### 2.3 SearchPlan 기반 자연어 검색

현재 SearchPlan은 프론트엔드 helper 중심으로 구현되어 있습니다.

현재 사용 중인 주요 필드:

- `originalQuery`
- `normalizedQuery`
- `correctionApplied`
- `correctionReason`
- `searchMode`
- `locationQuery`
- `baseLocationQuery`
- `targetQuery`
- `targetType`
- `categoryHint`
- `recommendationIntent`
- `preferredTags`
- `negativeTags`
- `kakaoKeywordCandidates`
- `confidence`
- `fallbackReason`

지원 검색 모드:

- `current_context`
- `around_location`
- `region_search`
- `simple_keyword`
- `recommendation_query`

현재 위치/지도 중심/특정 장소/특정 지역 기준 검색을 분리해 처리합니다.

---

### 2.4 카카오 검색 + DB 보강 + 병합

- 카카오 검색 결과를 기본 장소 후보로 사용합니다.
- 카카오 place id와 DB `Place.external_id`가 같으면 DB 태그/추천 정보를 붙입니다.
- 카카오 결과는 저장하지 않고 화면 표시용으로만 사용합니다.
- 결과 유형은 `카카오+DB`, `DB추천`, `카카오`로 구분합니다.
- 같은 장소는 아래 기준으로 중복 표시하지 않습니다.
  - `external_id === kakaoPlaceId`
  - 장소명 유사 + 좌표 30m 이내
  - 장소명 유사 + 주소 일부 일치

---

### 2.5 추천 결과 표시와 정렬

- `DB추천`과 `카카오+DB`는 추천 점수, 추천 이유, 추천 신뢰도, 매칭 태그를 표시합니다.
- `카카오`만 있는 결과는 추천 점수를 만들지 않고 외부 검색 후보로 표시합니다.
- 일반 검색에서는 태그/DB 정보가 있는 결과를 우선 표시하고, 같은 그룹 안에서는 거리순으로 정렬합니다.
- 추천 검색에서는 추천 점수, 태그 매칭, 거리, 부적합 후보 감점 등을 반영해 정렬합니다.

---

### 2.6 오타 보정과 추상 표현 처리

- 검색 전 공백 정리와 일부 오타/축약어 보정을 적용합니다.
  - `카패 -> 카페`
  - `와파이 -> 와이파이`
  - `콘샌트 -> 콘센트`
  - `놋북 -> 노트북`
  - `흡구 -> 흡연구역`
  - `공화 -> 공중화장실`
  - `공와 -> 공공와이파이`
  - `작엄 -> 작업`
- 보정이 적용되면 사용자에게 보정 문구를 표시합니다.
- 지역명/장소명은 무리하게 보정하지 않습니다.
- `곳`, `장소`, `데`, `갈만한 곳`, `쉴 곳`, `작업할 곳` 등은 추상 표현으로 보고 검색 가능한 카카오 후보 키워드를 생성합니다.

---

### 2.7 대표 장소/부속 시설 정렬

- 대표 장소 검색에서 `주차장`, `화장실`, `관리사무소`, `입구`, `정문`, `정류장` 같은 부속 시설이 과하게 상위에 오지 않도록 감점합니다.
- 사용자가 주차장/화장실/와이파이 같은 편의시설을 직접 찾는 경우에는 감점하지 않습니다.
- 1차 카카오 결과가 부속 시설뿐이면 대표 장소명을 추출해 보조 검색을 1회 수행합니다.

---

### 2.8 waiting_place 부적합 쉼터 필터링

- `waiting_place` 추천에서 일반 사용자가 잠깐 쉬기 어려운 제한 접근 쉼터를 강하게 제외하거나 후순위 처리합니다.
- 강한 제외/후순위 대상:
  - 경로당
  - 노인정
  - 노인회관
  - 마을회관
  - 사랑방
  - 사랑터
  - 복지관
  - 노인복지
  - 요양원
  - 어린이집
  - 유치원
  - 학교
- 행정복지센터, 주민센터, 동사무소, 구청, 시청, 민원센터 등은 잠깐 쉴 곳 검색에서 강한 감점을 적용합니다.
- 부적합 후보에는 “잠깐 쉬기 좋은 후보” 같은 긍정 추천 이유를 붙이지 않습니다.

---

### 2.9 카카오 상세/길찾기 연결

- DB추천 장소라도 `source=kakao_local`이고 `external_id`가 있으면 카카오 상세 URL을 생성합니다.
- 카카오 상세 URL이 있으면 DB 요약 카드보다 카카오 상세 iframe 또는 링크를 우선 표시합니다.
- 좌표가 있는 모든 장소에 “카카오맵 길찾기” 버튼을 표시합니다.
- 현재 위치 좌표가 있으면 출발지/도착지 길찾기 URL을 만들고, 없으면 도착지만 지정하는 URL로 fallback합니다.

---

### 2.10 데이터 seed 작업 상태

| 데이터 | 상태 |
|---|---|
| 카페 | ExternalPlaceTag용 seed 생성 완료 |
| 관광지 | PlaceTag seed 생성 완료 |
| 도시공원 | PlaceTag seed 생성 완료, 기본 태그 제거 기록 있음 |
| 해수욕장 | PlaceTag seed 생성 완료, 좌표 없는 1건 스킵 |
| 주차장 | PlaceTag seed 생성 완료, 기본 `주차장` 제거. category_rule 잔여 확인 필요 |
| 공중화장실 | PlaceTag seed 생성 완료, 기본/노이즈 태그 제거 완료 |
| 쉼터 | PlaceTag seed 생성 완료, `무더위쉼터` 태그 제외 여부는 최종 import 전 확인 필요. 현재 추천 로직에서는 제한 접근 쉼터를 강하게 필터링 |
| 무료와이파이 | Place 정제 완료, PlaceTag seed 생략 방향 |
| 흡연구역 | 세부 유형 태그 import 로직 정리 완료 |

---

### 2.11 모델 상태

- `Place`, `Tag`, `PlaceTag` 모델은 현재 사용 중
- `PlaceTag.source` choices에 `field_rule`, `keyword_rule`, `blog_search`, `external_api`, `external_data`, `ai_suggested`, `checked`, `user_verified`, `warning_tags` 반영됨
- `ExternalPlaceTag` 모델은 아직 없음
- 현재 구현은 `Place.external_id`와 카카오 place id를 기준으로 DB 태그/추천 정보를 보강함
- `ExternalPlaceTag`는 별도 모델로 추가할지 검토 필요
- `Place`에는 `category + lat + lng` 인덱스 추가가 작업트리에 반영되어 있으나, 마이그레이션 적용 여부는 별도 확인 필요

---

### 2.12 문서 최신화

다음 문서를 현재 기준으로 최신화했습니다.

```text
docs/04_recommendation/tagging-rule.md
docs/02_data/data-cleaning-policy.md
docs/03_planning/db-design.md
docs/02_data/tag-seed-summary.md
docs/01_progress/TodoKYB.md
docs/04_recommendation/search-plan-policy.md
```

---

## 3. 다음에 이어서 할 작업

다음에 “이어서 하자”라고 하면 아래 순서로 진행합니다.

```text
1. 통합 지도 검색 수동 테스트
2. 카카오+DB 병합 샘플 검증
3. DB추천 장소의 카카오 상세 URL 표시 검증
4. waiting_place 부적합 쉼터 상위 노출 여부 테스트
5. 대표 장소/부속 시설 정렬 테스트
6. 조건 충돌 검색 정책 구현 검토
7. 식당/음식/브랜드 검색 SearchPlan 개선
8. SearchPlan 백엔드 API화 검토
9. AI SearchPlan JSON 생성 방식 검토
10. 정제 데이터 import 작업 재개
```

추천 import 폴더 구조:

```text
backend/recommendations/fixtures/import_data/
├─ places/
├─ place_tags/
└─ external_place_tags/
```

원본 산출물은 삭제하거나 이동하지 않고, import용 복사본만 생성합니다.

---

## 4. 주의사항

- `.env`는 절대 커밋하지 않음
- 쉼터 API 키는 노출 이력이 있으므로 추후 재발급 권장
- 지도 API 검색 결과를 대량 저장하는 방식은 API 정책 확인 전까지 확정하지 않음
- 현재 카카오 검색 결과는 저장하지 않고 화면 표시용으로만 사용함
- 카카오/네이버/구글 지도 리뷰를 무단 크롤링해서 저장하지 않음
- AI는 실제 장소 정보를 생성하지 않고, 확보된 데이터의 태그 후보 생성/추천 이유 생성 보조로만 사용
- 조건 만족 여부를 확인할 수 없는 경우에는 가능하다고 단정하지 않고 “확인되지 않음”으로 안내해야 함
