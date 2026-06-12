# 태그 Seed 작업 정리

## 1. 문서 목적

이 문서는 상황 기반 생활 장소 추천 지도 서비스에서 사용하는 태그 seed 생성 작업의 기준과 현재 진행 상황을 정리한 문서입니다.

프로젝트의 핵심 방향은 단순 지도 조회가 아니라, 사용자의 위치와 상황에 맞는 장소를 추천하고 추천 결과를 지도에서 확인하는 것입니다. 따라서 태그는 장소를 설명하는 모든 단어를 저장하기 위한 용도가 아니라, 추천과 필터에 실제로 사용할 수 있는 세부 속성 정보를 저장하기 위한 용도로 관리합니다.

현재 태그 seed 작업은 외부 데이터, 공공데이터, 블로그 검색 결과, 키워드 규칙 등을 기반으로 장소별 추천 태그 후보를 생성하는 단계입니다. 모델 구조는 팀원이 수정 중이므로, 최종 `models.py` 확인 후 import 코드와 serializer 구조를 맞출 예정입니다.

---

## 2. 태그 저장 기본 원칙

### 2.1 Place.category로 알 수 있는 기본 태그는 저장하지 않음

장소의 카테고리만으로 이미 알 수 있는 너무 기본적인 태그는 `PlaceTag`에 저장하지 않습니다.

예시는 다음과 같습니다.

| 카테고리 | 저장하지 않는 기본 태그 예시 |
| --- | --- |
| 주차장 | 주차장 |
| 도시공원 | 공원 |
| 해수욕장 | 해수욕장, 바다 |
| 공중화장실 | 공중화장실, 생활편의 |
| 쉼터 | 쉼터, 무더위쉼터 |
| 무료 와이파이 | 무료와이파이 |
| 흡연구역 | 흡연구역 |

기본 카테고리 정보는 `Place.category`에서 관리하고, `PlaceTag`에는 추천과 필터에 실제로 도움이 되는 세부 속성만 저장하는 방향입니다.

---

### 2.2 추천/필터에 사용할 세부 속성 태그만 저장

`PlaceTag`에는 사용자의 상황 기반 추천에 활용 가능한 세부 속성 태그를 저장합니다.

예시는 다음과 같습니다.

| 분야 | 저장할 수 있는 세부 태그 예시 |
| --- | --- |
| 주차장 | 무료주차, 24시간운영후보, 야간운영후보, 공영주차장 |
| 공중화장실 | 장애인화장실있음, 기저귀교환대있음, 남녀분리, 24시간개방후보 |
| 쉼터 | 냉방시설있음, 실내쉼터, 야간운영후보, 주말휴일개방, 수용인원많음 |
| 관광지 | 야경, 산책좋음, 가족나들이, 사진찍기좋음 |
| 도시공원 | 산책좋음, 운동시설있음, 휴식좋음, 반려동물동반후보 |
| 해수욕장 | 산책좋음, 야경, 가족나들이, 사진찍기좋음 |
| 카페 후보 | 노트북작업후보, 조용한카페후보, 감성카페후보, 혼자이용후보 |

태그는 확정 정보와 후보 정보를 구분해야 합니다. 예를 들어 블로그 검색 기반 태그나 AI 추천 태그는 사실 확정 정보가 아니라 후보 정보로 다룹니다.

---

## 3. 태그 저장 구조와 화면 출력 구조 분리

태그의 저장 구조와 화면 출력 구조는 분리합니다.

DB에는 태그가 생성된 근거를 자세히 남기기 위해 `source`를 세분화해서 저장합니다. 반면 화면과 API 응답에서는 사용자가 이해하기 쉽도록 여러 source를 묶어서 보여줍니다.

예를 들어 DB에는 `field_rule`, `keyword_rule`, `blog_search`, `team_checked`처럼 세부 출처를 저장하고, 화면에서는 이를 `데이터 기반 태그`, `블로그 태그`, `검수 태그`처럼 묶어서 보여줍니다.

`display_group`은 별도 모델 필드로 저장하기보다 serializer 또는 모델 메서드에서 계산하는 방향이 적절합니다. 이유는 화면 출력 정책이 바뀌더라도 DB 구조를 바꾸지 않고 대응할 수 있기 때문입니다.

---

## 4. 태그 source 구분 기준

현재 사용하는 태그 source 구분은 다음과 같습니다.

| 구분 | 내부 이름 후보 | 설명 | 저장 여부 |
| --- | --- | --- | --- |
| 기본 태그 | default_tags / category_rule | 카테고리만 보고 자동으로 붙는 태그 | 너무 기본적인 건 저장하지 않음 |
| 원본 필드 태그 | field_rule | 공공데이터 원본 필드에서 나온 태그 | 저장 |
| 키워드 규칙 태그 | keyword_rule | 장소명, 시설명, 주소, 설명의 키워드로 붙인 태그 | 저장 |
| 블로그 태그 | blog_search | 네이버 블로그 검색 결과 기반 후보 태그 | 저장, 후보 |
| 외부 API 태그 | external_api | 카카오/관광공사 등 외부 API 결과 기반 태그 | 저장, 상황별 |
| AI 후보 태그 | ai_suggested | AI가 추천한 후보 태그 | 저장, 후보 |
| 팀 검수 태그 | team_checked | 팀원이 직접 확인한 태그 | 저장, 신뢰도 높음 |
| 관리자 검수 태그 | admin_checked | 관리자가 승인/수정한 태그 | 저장, 신뢰도 높음 |
| 사용자 검증 태그 | user_verified | 사용자가 검증한 태그 | 저장, 운영 후 |
| 확인 필요 태그 | warning_tags / needs_verification | 정보 부족, 확인 필요 태그 | 저장 |

주의할 점은 `category_rule` 자체를 무조건 금지하는 것이 아니라, 카테고리만으로 알 수 있는 너무 기본적인 태그를 제거한다는 점입니다. 추천과 필터에 의미가 있는 카테고리 기반 세부 태그라면 저장 여부를 별도로 판단할 수 있습니다.

---

## 5. 화면/API 출력 그룹 기준

화면에서는 세부 source를 그대로 모두 보여주기보다 다음과 같이 묶어서 보여줍니다.

| 화면 출력 그룹 | 포함 source 또는 조건 | 설명 |
| --- | --- | --- |
| 검수 태그 | team_checked, admin_checked | 팀 또는 관리자가 확인한 신뢰도 높은 태그 |
| 데이터 기반 태그 | category_rule, field_rule, keyword_rule, external_data, external_api | 원본 데이터, 키워드 규칙, 외부 API 기반 태그 |
| 블로그 태그 | blog_search | 블로그 검색 결과 기반 후보 태그 |
| AI 후보 태그 | ai_suggested | AI가 추천한 후보 태그 |
| 사용자 검증 태그 | user_verified | 사용자가 검증한 태그 |
| 확인 필요 태그 | status=needs_verification 또는 tag_type=warning | 정보 부족 또는 확인이 필요한 태그 |

현재 source 목록에서는 `external_api`를 사용하고 있으나, 화면 그룹 기준에는 `external_data`도 함께 언급되어 있습니다. 최종 모델 확정 시 `external_data`를 별도 source로 둘지, `field_rule` 또는 `external_api`에 포함할지 확인이 필요합니다.

---

## 6. 카테고리별 seed 생성 현황

### 6.1 카페

카페는 현재 실제 `Place`로 저장하기보다, Kakao Local 기반 외부 장소 태그 후보로 관리하는 방향입니다.

| 항목 | 내용 |
| --- | --- |
| 저장 대상 | ExternalPlaceTag용 seed |
| 주요 데이터 기반 | Kakao Local 기반 외부 장소 후보 |
| 결과 파일 | `Test/apiTest/tag/cafeTag/outputs/cafe_external_place_tags_seed.json` |
| 장소 수 | 668개 |
| row 수 | 2818 row |
| 비고 | Place에 직접 저장하지 않고 외부 후보 태그로 관리 |

카페의 조용함, 노트북 작업 가능, 콘센트 있음, 혼자 이용 좋음 같은 정보는 공공데이터만으로 확정하기 어렵습니다. 따라서 현재 단계에서는 외부 장소 후보와 태그 후보로 분리해 관리하는 것이 적절합니다.

---

### 6.2 관광지

관광지는 관광공사 공식 관광지 데이터를 기반으로 `Place` 저장이 가능한 카테고리입니다. 블로그 기반 태그는 `PlaceTag` 후보로 생성했습니다.

| 항목 | 내용 |
| --- | --- |
| 저장 대상 | PlaceTag seed |
| 주요 데이터 기반 | 관광공사 공식 관광지 + 블로그 검색 기반 태그 후보 |
| 결과 파일 | `Test/apiTest/tag/tourTag/tourist_spot_busan_place_tag_seed.json` |
| 장소 수 | 311개 |
| row 수 | 1003 row |
| 비고 | 블로그 기반 태그는 후보 정보로 관리 |

---

### 6.3 도시공원

도시공원은 `PlaceTag` seed 생성을 완료했고, 기본 `category_rule` 태그는 제거했습니다.

| 항목 | 내용 |
| --- | --- |
| 저장 대상 | PlaceTag seed |
| 결과 파일 | `Test/apiTest/tag/parkTag/park_place_tag_seed.json` |
| 기존 row 수 | 190318 row |
| 처리 내용 | 기본 category_rule 태그 제거 완료 |

도시공원의 경우 `공원`처럼 카테고리만으로 알 수 있는 태그는 저장하지 않고, 추천에 사용할 수 있는 세부 속성 태그 위주로 관리합니다.

---

### 6.4 해수욕장

해수욕장은 `PlaceTag` seed 생성을 완료했고, 기본 `category_rule` 태그를 제거했습니다.

| 항목 | 내용 |
| --- | --- |
| 저장 대상 | PlaceTag seed |
| 결과 파일 | `Test/apiTest/tag/beachTag/beach_place_tag_seed.json` |
| 장소 수 | 281개 |
| 기존 row 수 | 2455 row |
| 처리 내용 | category_rule 제거 완료 |

해수욕장, 바다처럼 카테고리만으로 알 수 있는 태그는 저장하지 않는 방향입니다.

---

### 6.5 주차장

주차장은 `PlaceTag` seed 생성을 완료했습니다. `field_warning`은 `field_rule`로 통합했고, 기본 태그인 `주차장`은 제거했습니다.

| 항목 | 내용 |
| --- | --- |
| 저장 대상 | PlaceTag seed |
| 결과 파일 | `Test/apiTest/tag/parkingTag/parking_place_tag_seed.json` |
| 장소 수 | 17540개 |
| 최종 생성 전 기준 row 수 | 174547 row |
| source 최종 | field_rule, category_rule |
| 처리 내용 | field_warning을 field_rule로 통합, 기본 태그 주차장 제거 |

주차장은 실시간 주차 가능 대수까지 구현하지 않습니다. 현재 단계에서는 무료 여부, 운영시간 후보, 공영 여부 등 정적 데이터 기반 추천 태그를 우선 사용합니다.

---

### 6.6 공중화장실

공중화장실은 `PlaceTag` seed 생성을 완료했습니다. 기본 태그와 추천에 부적합한 노이즈 태그를 제거했습니다.

| 항목 | 내용 |
| --- | --- |
| 저장 대상 | PlaceTag seed |
| 결과 파일 | `Test/apiTest/tag/toiletTag/toilet_place_tag_seed.json` |
| 최종 row 수 | 112610 row |
| 제거한 기본 태그 | 공중화장실, 생활편의 |
| 제거한 노이즈 태그 | 오물처리방식정보있음, 남녀화장실정보있음, 연락처있음, 개방시간정보있음 |

공중화장실은 장애인화장실, 기저귀교환대, 남녀분리, 24시간개방후보처럼 실제 사용 상황에 영향을 주는 태그만 유지하는 방향입니다.

---

### 6.7 쉼터

쉼터는 재난안전데이터공유플랫폼의 행정안전부 무더위쉼터 API를 사용해 수집했습니다.

| 항목 | 내용 |
| --- | --- |
| API | 재난안전데이터공유플랫폼 행정안전부_무더위쉼터 API |
| API URL | `https://www.safetydata.go.kr/V2/api/DSSP-IF-10942` |
| totalCount | 59887 |
| 실제 반환 특성 | `numOfRows`를 크게 줘도 실제 1000건씩 반환 |
| 수집 방식 | 실제 반환 수 기준으로 60페이지 수집 |
| 최종 수집 item 수 | 59887 |

수집 결과 파일은 다음과 같습니다.

| 구분 | 파일 |
| --- | --- |
| 원본 전체 응답 | `ExData/JsonData/shelter/shelter_api_raw.json` |
| 원본 item 목록 | `ExData/JsonData/shelter/shelter_api_items.json` |
| 수집 요약 | `ExData/JsonData/shelter/shelter_api_summary.json` |
| 정제 결과 | `ExData/Cleaned/shelter_places.json` |
| 정제 스킵 결과 | `ExData/Cleaned/skipped/shelter_skipped.json` |
| PlaceTag seed | `Test/apiTest/tag/shelterTag/shelter_place_tag_seed.json` |
| PlaceTag seed 요약 | `Test/apiTest/tag/shelterTag/shelter_place_tag_seed_summary.json` |

쉼터 PlaceTag seed 생성 결과는 다음과 같습니다.

| 항목 | 수치 |
| --- | ---: |
| 입력 쉼터 수 | 59887 |
| 입력 스킵 수 | 0 |
| PlaceTag seed 장소 수 | 59887 |
| PlaceTag seed row 수 | 327090 |
| 스킵 수 | 0 |
| 기본/노이즈 태그 제거 수 | 203128 |

주요 태그는 다음과 같습니다.

| 태그 | 수량 |
| --- | ---: |
| 무더위쉼터 | 59887 |
| 냉방시설있음 | 56611 |
| 실내쉼터 | 52891 |
| 선풍기있음 | 50822 |
| 복지시설쉼터 | 46242 |
| 규모큰쉼터후보 | 24595 |
| 야간운영후보 | 15410 |
| 수용인원많음 | 7616 |
| 주말휴일개방 | 5474 |
| 숙박가능후보 | 2473 |
| 공공시설쉼터 | 2359 |
| 24시간운영후보 | 1717 |
| 야외쉼터 | 983 |
| 한파쉼터후보 | 9 |
| 운영시간확인필요 | 1 |

쉼터의 경우 `무더위쉼터`는 기본 카테고리 성격이 강하므로 최종 import 대상에서는 제외 여부를 다시 확인해야 합니다. 반면 `냉방시설있음`, `실내쉼터`, `야간운영후보`, `주말휴일개방`, `수용인원많음` 등은 추천과 필터에 활용 가능성이 높습니다.

---

## 7. 흡연구역 / 무료와이파이 처리 방향

### 7.1 흡연구역

흡연구역은 태그보다 위치 데이터 자체가 중요한 카테고리입니다. 따라서 현재 단계에서는 `Place.category=smoking_area`로 충분할 가능성이 높습니다.

다만 원본 데이터에서 세부 구분이 가능하다면 다음 정도의 태그만 검토합니다.

- 실내흡연실
- 실외흡연구역
- 부스형흡연구역
- 개방형흡연구역

세부 구분 근거가 부족하다면 억지로 `PlaceTag` seed를 만들지 않는 것이 좋습니다.

---

### 7.2 무료와이파이

무료와이파이도 태그보다 위치 데이터 자체가 중요한 카테고리입니다. 따라서 현재 단계에서는 `Place.category=free_wifi`로 충분할 가능성이 높습니다.

추천과 필터에 사용할 세부 속성이 없다면 `PlaceTag` seed를 생략하는 것이 적절합니다.

---

## 8. Git LFS 관리 대상

대용량 seed 파일과 수집 원본 파일은 Git LFS로 관리합니다.

현재 LFS 관리가 필요한 주요 파일은 다음과 같습니다.

```text
ExData/JsonData/shelter/*.json
ExData/Cleaned/shelter_places.json
ExData/Cleaned/skipped/shelter_skipped.json
Test/apiTest/tag/shelterTag/shelter_place_tag_seed.json
Test/apiTest/tag/toiletTag/toilet_place_tag_seed.json
Test/apiTest/tag/parkingTag/parking_place_tag_seed.json
Test/apiTest/tag/parkTag/park_place_tag_seed.json
기타 100MB 초과 seed JSON
```

GitHub의 일반 파일 업로드 제한 때문에 100MB를 초과하는 파일은 반드시 LFS 대상으로 관리해야 합니다.

---

## 9. 보안 및 API 키 주의사항

`.env` 파일에는 `SHELTER_API_KEY`가 포함되어 있으므로 절대 커밋하면 안 됩니다.

한 번 서비스키가 로그에 노출된 이력이 있으므로, 추후 서비스키 재발급을 권장합니다.

쉼터 API는 IP 등록 이슈가 있었고, 사용자 IP를 승인 처리한 뒤 정상 수집되었습니다. 추후 다른 환경에서 다시 수집할 경우 IP 승인 여부를 먼저 확인해야 합니다.

---

## 10. 모델 확인 필요 사항

팀원이 수정한 최종 `models.py` 확인 후 다음 항목을 반드시 확인해야 합니다.

### 10.1 PlaceTag 관련 확인

- `PlaceTag.source` choices에 다음 값이 포함되어 있는지 확인
  - `field_rule`
  - `keyword_rule`
  - `blog_search`
  - `external_api`
  - `ai_suggested`
  - `team_checked`
  - `admin_checked`
  - `user_verified`
- `status` 또는 유사 필드로 후보/확정/확인필요 상태를 구분할 수 있는지 확인
- `confidence` 또는 신뢰도 점수를 저장할 수 있는지 확인
- 같은 장소에 같은 태그가 중복 저장되지 않도록 unique 제약이 있는지 확인

### 10.2 ExternalPlaceTag 관련 확인

- 카페처럼 `Place`에 직접 저장하지 않는 외부 장소 후보를 위한 `ExternalPlaceTag` 모델이 있는지 확인
- 외부 장소명, 외부 API 제공자, external_id, 좌표, 주소, 태그 후보를 저장할 수 있는지 확인
- 외부 API 결과를 대량 저장하는 방식이 API 정책에 맞는지 확인 필요

### 10.3 Tag 관련 확인

- `Tag.tag_type` choices가 다음 구조를 지원하는지 확인
  - `category`
  - `recommendation`
  - `warning`
- 기본 카테고리 태그와 추천용 세부 태그를 구분할 수 있는지 확인

### 10.4 Place 관련 확인

- `Place.source`와 `Place.external_id`를 통해 외부 데이터 출처와 원본 ID를 관리할 수 있는지 확인
- `Place.source + external_id` unique 구조가 유지되는지 확인
- 좌표, 주소, 카테고리, 최신 확인일을 저장할 수 있는지 확인

---

## 11. 다음 작업

현재 단계에서 이어서 할 작업은 다음 순서가 적절합니다.

1. 팀원이 수정한 최종 `models.py` 확인
2. `PlaceTag.source`, `Tag.tag_type`, `ExternalPlaceTag`, `Place.source + external_id` 구조 확인
3. 각 seed JSON의 실제 필드 구조 확인
4. `import_place_tags.py` 작성
5. `import_external_place_tags.py` 작성
6. serializer에서 `display_group` 계산 로직 작성
7. 화면에서 태그 그룹별 출력 확인

---

## 12. 현재 판단 요약

현재 태그 seed 작업은 추천 서비스에 필요한 세부 속성 태그를 모으는 방향으로 진행되고 있습니다.

카테고리만으로 알 수 있는 기본 태그는 `Place.category`에서 처리하고, `PlaceTag`에는 추천과 필터에 필요한 세부 태그만 저장하는 방향이 적절합니다.

DB에는 태그의 출처를 자세히 저장하고, 화면/API에서는 사용자가 이해하기 쉽게 그룹화해서 보여주는 구조가 좋습니다.

흡연구역과 무료와이파이는 위치 중심 카테고리이므로, 세부 속성이 부족하다면 `PlaceTag` seed를 무리하게 만들지 않아도 됩니다.

이후에는 최종 모델 구조를 확인한 뒤 import 코드와 serializer 출력 구조를 맞추는 작업이 필요합니다.
