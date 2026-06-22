# DB 설계서

## 1. 설계 목적

본 문서는 상황 기반 생활 장소 추천 지도 서비스의 현재 Django 모델 구조와 향후 확장 방향을 정리합니다.

서비스의 핵심은 단순 지도 조회가 아니라, 사용자의 위치와 상황을 기반으로 지금 필요한 생활 장소를 추천하고 추천 결과를 지도에서 확인하는 것입니다. 초기 추천은 머신러닝보다 규칙 기반으로 구현하며, 장소의 카테고리, 태그, 거리, 최신성, 신뢰도, 확인 필요 여부를 조합합니다.

---

## 2. 현재 모델 기준

현재 `kyb` 브랜치의 핵심 모델은 다음과 같습니다.

| 모델 | 상태 | 설명 |
|---|---|---|
| `Place` | 구현됨 | 실제 DB에 저장하는 장소 정보 |
| `Tag` | 구현됨 | 추천/필터에 사용하는 태그 사전 |
| `PlaceTag` | 구현됨 | Place와 Tag의 연결, 출처, 상태, 신뢰도 관리 |
| `ExternalPlaceTag` | 아직 없음 | 카페처럼 Place에 저장하지 않는 외부 장소 후보 태그 저장용으로 검토했던 예정 모델. 현재 구현은 우선 `Place.external_id`와 카카오 place id 매칭을 사용 |
| `Category` | 별도 모델 없음 | 현재는 `Place.category` 문자열 필드로 관리 |

현재 구현은 별도 `Category` 테이블을 두지 않고, `Place.category` 문자열로 카테고리를 관리합니다. 문서나 ERD를 작성할 때도 현재 구현 기준을 우선합니다.

---

## 3. Place

`Place`는 실제 추천 대상이 되는 장소 정보를 저장합니다.

### 3.1 주요 필드

| 필드 | 설명 |
|---|---|
| `name` | 장소명 |
| `category` | 장소 카테고리 문자열. 예: `toilet`, `parking`, `free_wifi`, `smoking_area` |
| `address` | 주소 |
| `lat` | 위도 |
| `lng` | 경도 |
| `source` | 데이터 출처 코드 |
| `external_id` | 원본 데이터의 외부 식별자 |
| `source_name` | 데이터 출처명 |
| `source_updated_at` | 원본 데이터 기준일 또는 갱신일 |
| `detail_location` | 상세 위치 |
| `data_quality_status` | 데이터 품질 상태 |
| `data_quality_score` | 데이터 품질 점수 |
| `raw` | 원본 행 데이터 |
| `created_at` | 생성일 |
| `updated_at` | 수정일 |

### 3.2 unique 기준

같은 외부 데이터를 중복 저장하지 않기 위해 아래 조합을 unique로 관리합니다.

```text
source + external_id
```

---

## 4. Tag

`Tag`는 추천과 필터에 사용할 태그 사전입니다.

### 4.1 주요 필드

| 필드 | 설명 |
|---|---|
| `name` | 태그명. unique |
| `tag_type` | 태그 유형 |
| `description` | 태그 설명 |

### 4.2 tag_type 기준

현재 모델의 `Tag.tag_type` 기준은 다음과 같습니다.

| tag_type | 설명 | 예시 |
|---|---|---|
| `category` | 카테고리 또는 분류 성격의 태그 | 어린이공원, 근린공원 등. 단, 너무 기본적인 태그는 저장하지 않음 |
| `recommendation` | 추천/필터에 사용할 세부 속성 태그 | 무료주차, 야경, 산책좋음, 냉방시설있음 |
| `warning` | 확인 필요 또는 주의 태그 | 요금정보확인필요, 운영시간확인필요 |

---

## 5. PlaceTag

`PlaceTag`는 장소와 태그를 연결하는 중간 모델입니다. 단순 ManyToMany가 아니라, 태그가 붙은 출처, 상태, 신뢰도, 근거를 함께 저장합니다.

### 5.1 주요 필드

| 필드 | 설명 |
|---|---|
| `place` | 연결된 Place |
| `tag` | 연결된 Tag |
| `source` | 태그 생성 출처 |
| `status` | 태그 상태 |
| `confidence` | 신뢰도 점수, 0~100 |
| `evidence` | 태그 부여 근거 |
| `is_verified` | 검증 여부 |
| `verified_at` | 검증 시각 |
| `created_at` | 생성일 |
| `updated_at` | 수정일 |

### 5.2 source 기준

현재 모델의 `PlaceTag.source` 기준은 다음과 같습니다.

| source | 설명 |
|---|---|
| `category_rule` | 카테고리 기반 규칙 태그. 너무 기본적인 태그는 저장하지 않음 |
| `field_rule` | 공공데이터 원본 필드 기반 태그 |
| `keyword_rule` | 장소명, 시설명, 주소, 설명 키워드 기반 태그 |
| `blog_search` | 블로그 검색 기반 후보 태그 |
| `external_api` | 카카오, 관광공사 등 외부 API 기반 태그 |
| `external_data` | CSV, JSON, 지자체 파일 등 외부 원본 데이터 기반 태그 |
| `ai_suggested` | AI 추천 후보 태그 |
| `checked` | 팀 또는 관리자 검수 완료 태그 |
| `user_verified` | 사용자 검증 태그 |
| `warning_tags` | 확인 필요 태그 |

현재 모델은 `team_checked`와 `admin_checked`를 분리하지 않고 `checked`로 관리합니다. 운영 단계에서 관리 주체를 분리할 필요가 있으면 source choices를 확장할 수 있습니다.

### 5.3 status 기준

| status | 설명 |
|---|---|
| `confirmed` | 확인된 태그 |
| `candidate` | 후보 태그 |
| `needs_verification` | 확인 필요 태그 |
| `rejected` | 반려 태그 |

### 5.4 unique 기준

같은 장소에 같은 태그가 같은 출처로 중복 저장되지 않도록 아래 조합을 unique로 관리합니다.

```text
place + tag + source
```

---

## 6. 외부 카카오 장소 태그 관리 방향

현재 구현은 별도 `ExternalPlaceTag` 모델 없이, 카카오 place id와 DB `Place.external_id`를 매칭하여 저장 태그/추천 정보를 보강합니다.

카카오 검색 결과는 화면 표시용 후보로 사용하고 DB에 즉시 저장하지 않습니다. 같은 카카오 place id를 가진 DB Place가 있으면 `카카오+DB` 결과로 병합합니다.

`ExternalPlaceTag` 모델은 여전히 검토 가능한 개선안이지만, 현재 구현 완료 기능으로 보지 않습니다.

### 6.1 ExternalPlaceTag 검토 배경

카페 태그 seed는 카카오 Local API 검색 결과의 place id와 매칭하기 위한 데이터입니다. 이 카페들을 전부 `Place`로 저장하면 외부 API 저장 정책, 데이터 최신성, 중복 관리 문제가 생길 수 있습니다.

초기 설계에서는 카페를 다음 구조로 관리하는 방안을 검토했습니다.

```text
카카오 API 검색 결과
→ external_id 또는 kakao_place_id 매칭
→ ExternalPlaceTag 후보 태그 조회
→ 추천 응답에 후보 태그와 추천 이유 표시
```

현재는 이 구조 대신 `Place.external_id` 기반 병합을 먼저 사용합니다.

### 6.2 후보 필드

| 필드 | 설명 |
|---|---|
| `provider` | 외부 API 제공자. 예: `kakao_local` |
| `external_id` | 외부 장소 ID. 카카오 place id 등 |
| `place_name` | 외부 장소명 |
| `category_name` | 외부 API 카테고리명 |
| `address` | 주소 |
| `lat` | 위도 |
| `lng` | 경도 |
| `tag` | 연결된 Tag |
| `source` | 태그 출처. 예: `blog_search`, `external_api`, `ai_suggested` |
| `status` | 후보/확정/확인필요 상태 |
| `confidence` | 신뢰도 |
| `evidence` | 태그 근거 |
| `raw` | 원본 또는 seed 데이터 |
| `created_at` | 생성일 |
| `updated_at` | 수정일 |

### 6.3 unique 후보

```text
provider + external_id + tag + source
```

---

## 7. 데이터별 저장 구조

| 데이터 | Place 저장 | PlaceTag 저장 | ExternalPlaceTag 저장 |
|---|---:|---:|---:|
| 공중화장실 | O | O | X |
| 주차장 | O | O | X |
| 도시공원 | O | O | X |
| 해수욕장 | O | O | X |
| 쉼터 | O | O | X |
| 흡연구역 | O | 조건부 | X |
| 무료와이파이 | O | X | X |
| 카페 후보 | X | X | O |
| 관광지 | O | O | X |

---

## 8. 추천과의 연결

초기 추천 점수는 다음 요소를 조합합니다.

```text
추천 점수 =
카테고리 일치 점수
+ 태그 일치 점수
+ 거리 점수
+ 태그 신뢰도 점수
+ 최신 확인 점수
- 확인 필요 태그 감점
- 오류 제보 감점
```

생활 인프라 데이터는 DB의 `Place`, `PlaceTag`를 기준으로 추천합니다.

현재 지도 검색에서는 카카오 API 검색 결과를 기본 후보로 사용하고, 카카오 place id와 `Place.external_id`가 일치하는 DB 장소가 있으면 저장 태그/추천 정보를 붙입니다.

DB 태그가 없는 카카오 결과는 추천 점수와 추천 이유를 만들지 않고 외부 검색 후보로 표시합니다.

조건 만족 여부를 확인할 수 없는 경우에는 가능하다고 단정하지 않고 “확인되지 않음” 또는 세부 태그 데이터 없음으로 안내해야 합니다.

---

## 8.1 SearchPlan 백엔드화 검토

현재 자연어 검색 SearchPlan은 프론트엔드 helper 중심으로 구현되어 있습니다.

향후 백엔드 API로 이전할 경우 SearchPlan은 다음 구조를 반환하는 방향으로 검토합니다.

```text
location + target + conditions + fallbackTargets + resultPolicy
```

백엔드화 시 고려할 점:

- AI는 실제 장소명, 주소, 좌표, 시설 보유 여부를 생성하지 않습니다.
- 음식/브랜드/장소 카테고리는 target으로 처리합니다.
- 흡연 가능, 콘센트 있음, 주차 가능 같은 조건은 conditions로 처리합니다.
- 조건을 만족하는 target이 없으면 fallbackTargets를 별도 그룹으로 표시합니다.
- 임베딩 기반 의미 매칭은 하드코딩 키워드 매핑을 줄이기 위한 향후 개선입니다.

---

## 9. 다음 모델 작업

1. 통합 지도 검색에서 필요한 DB 장소/태그 샘플 검증
2. `Place.external_id` 기반 카카오+DB 병합 정확도 확인
3. `ExternalPlaceTag` 모델이 필요한지 재검토
4. 필요 시 `ExternalPlaceTag` 모델 추가
5. 정제 데이터 import 스크립트 작성
6. SearchPlan 백엔드 API 설계
