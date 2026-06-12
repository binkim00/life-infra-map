# 태그 Seed 작업 정리

## 1. 문서 목적

이 문서는 상황 기반 생활 장소 추천 지도 서비스에서 사용하는 태그 seed 생성 작업의 기준과 현재 진행 상황을 정리합니다.

태그는 장소를 설명하는 모든 단어를 저장하기 위한 용도가 아니라, 추천과 필터에 실제로 사용할 수 있는 세부 속성 정보를 저장하기 위한 용도로 관리합니다.

---

## 2. 태그 저장 원칙

### 2.1 기본 태그는 저장하지 않음

`Place.category`만으로 이미 알 수 있는 태그는 `PlaceTag`에 저장하지 않습니다.

| 카테고리 | 저장하지 않는 기본 태그 예시 |
|---|---|
| 주차장 | 주차장 |
| 도시공원 | 공원, 도시공원 |
| 해수욕장 | 해수욕장, 바다 |
| 공중화장실 | 공중화장실, 생활편의 |
| 쉼터 | 쉼터 |
| 무료와이파이 | 무료와이파이, 와이파이 |
| 흡연구역 | 흡연구역, 흡연, 흡연가능 |

기본 카테고리 정보는 `Place.category`에서 관리하고, `PlaceTag`에는 추천과 필터에 실제로 도움이 되는 세부 속성만 저장합니다.

---

### 2.2 세부 속성 태그만 저장

저장 대상은 다음과 같은 태그입니다.

```text
무료주차
24시간운영후보
장애인화장실있음
기저귀교환대있음
냉방시설있음
야간운영후보
산책좋음
야경
드라이브목적지
실내흡연실
부스형흡연구역
```

---

### 2.3 저장 구조와 화면 출력 구조 분리

DB에는 source를 세분화해서 저장합니다. 화면/API 응답에서는 source를 그대로 보여주기보다 `검수 태그`, `데이터 기반 태그`, `블로그 태그`, `AI 후보 태그`, `확인 필요 태그`처럼 묶어서 보여줍니다.

`display_group`은 모델 필드로 저장하지 않고 serializer 또는 모델 메서드에서 계산합니다.

---

## 3. source 기준

현재 `kyb` 브랜치 기준 source는 다음과 같습니다.

| source | 설명 |
|---|---|
| `category_rule` | 카테고리 기반 규칙 태그. 너무 기본적인 태그는 저장하지 않음 |
| `field_rule` | 공공데이터 원본 필드 기반 태그 |
| `keyword_rule` | 장소명, 시설명, 주소, 설명 키워드 기반 태그 |
| `blog_search` | 블로그 검색 기반 후보 태그 |
| `external_api` | 외부 API 기반 태그 |
| `external_data` | CSV, JSON, 지자체 파일 등 외부 원본 데이터 기반 태그 |
| `ai_suggested` | AI 추천 후보 태그 |
| `checked` | 팀 또는 관리자 검수 완료 태그 |
| `user_verified` | 사용자 검증 태그 |
| `warning_tags` | 확인 필요 태그 |

현재 모델에는 `team_checked`, `admin_checked`가 따로 없고 `checked`로 통합되어 있습니다.

---

## 4. 카테고리별 seed 생성 현황

### 4.1 카페

| 항목 | 내용 |
|---|---|
| 저장 대상 | ExternalPlaceTag용 seed |
| 주요 데이터 기반 | Kakao Local 기반 외부 장소 후보 + 블로그 태그 후보 |
| 결과 파일 | `Test/apiTest/tag/cafeTag/outputs/cafe_external_place_tags_seed.json` |
| 장소 수 | 668개 |
| row 수 | 2818 row |
| 상태 | 완료 |

카페 장소는 현재 `Place`에 직접 저장하지 않습니다. 카카오 Local API 검색 결과의 place id와 매칭하기 위한 `ExternalPlaceTag` seed로 관리합니다.

---

### 4.2 관광지

| 항목 | 내용 |
|---|---|
| 저장 대상 | PlaceTag seed |
| 주요 데이터 기반 | 관광공사 공식 관광지 + 블로그 검색 기반 태그 후보 |
| 결과 파일 | `Test/apiTest/tag/tourTag/tourist_spot_busan_place_tag_seed.json` |
| 장소 수 | 311개 |
| row 수 | 1003 row |
| 상태 | 완료 |

관광공사 공식 관광지는 `Place`로 저장 가능하며, 블로그 기반 태그는 `candidate` 상태로 관리합니다.

---

### 4.3 도시공원

| 항목 | 내용 |
|---|---|
| 저장 대상 | PlaceTag seed |
| 결과 파일 | `Test/apiTest/tag/parkTag/park_place_tag_seed.json` |
| 입력 장소 수 | 18376개 |
| seed 장소 수 | 18232개 |
| 최종 row 수 | 130792 row |
| 제거 row 수 | 59526 row |
| 상태 | 거의 완료 |

기본 태그 및 전역 기본 태그로 판단한 `공원`, `산책좋음`, `잠깐쉬기좋음`, `쉼터`, `화장실` 일부를 제거했습니다. 남은 태그는 field_rule과 blog_search 기반 후보 태그입니다.

---

### 4.4 해수욕장

| 항목 | 내용 |
|---|---|
| 저장 대상 | PlaceTag seed |
| 결과 파일 | `Test/apiTest/tag/beachTag/beach_place_tag_seed.json` |
| 입력 장소 수 | 282개 |
| seed 장소 수 | 281개 |
| 최종 row 수 | 1612 row |
| 스킵 | 좌표 없는 다대포서측 1건 |
| 제거 row 수 | 843 row |
| 상태 | 거의 완료 |

`해수욕장`, `바다`, `물놀이` 기본 태그를 제거했습니다.

---

### 4.5 주차장

| 항목 | 내용 |
|---|---|
| 저장 대상 | PlaceTag seed |
| 결과 파일 | `Test/apiTest/tag/parkingTag/parking_place_tag_seed.json` |
| 장소 수 | 17540개 |
| 최종 row 수 | 157007 row |
| 제거 row 수 | 17540 row |
| 상태 | 거의 완료, 잔여 category_rule 확인 필요 |

`주차장` 기본 태그는 제거했습니다. 다만 summary 기준 `category_rule`이 35080건 남아 있으므로, 이 값들이 기본 태그인지 추천에 의미 있는 세부 분류인지 최종 import 전 확인이 필요합니다.

주요 태그 예시:

```text
평일운영
주말운영
야간운영후보
공영주차장
24시간운영후보
무료주차
유료주차
장애인주차구역있음
요금정보확인필요
```

---

### 4.6 공중화장실

| 항목 | 내용 |
|---|---|
| 저장 대상 | PlaceTag seed |
| 결과 파일 | `Test/apiTest/tag/toiletTag/toilet_place_tag_seed.json` |
| 장소 수 | 29132개 |
| 최종 row 수 | 112610 row |
| 제거 기본 태그 수 | 58264 row |
| 제거 노이즈 태그 수 | 96026 row |
| 상태 | 완료 |

제거한 기본 태그:

```text
공중화장실
생활편의
```

제거한 노이즈 태그:

```text
오물처리방식정보있음
남녀화장실정보있음
연락처있음
개방시간정보있음
```

---

### 4.7 쉼터

| 항목 | 내용 |
|---|---|
| 저장 대상 | PlaceTag seed |
| API | 재난안전데이터공유플랫폼 행정안전부_무더위쉼터 API |
| API URL | `https://www.safetydata.go.kr/V2/api/DSSP-IF-10942` |
| 최종 수집 item 수 | 59887개 |
| PlaceTag seed 장소 수 | 59887개 |
| PlaceTag seed row 수 | 327090 row |
| 기본/노이즈 태그 제거 수 | 203128 row |
| 상태 | 거의 완료, 무더위쉼터 제외 여부 확인 필요 |

주요 태그:

```text
무더위쉼터
냉방시설있음
실내쉼터
선풍기있음
복지시설쉼터
규모큰쉼터후보
야간운영후보
수용인원많음
주말휴일개방
숙박가능후보
```

`쉼터` 기본 태그와 정보 존재 여부 태그는 제거했습니다. 다만 `무더위쉼터`는 현재 tag_counts에 남아 있으므로, 최종 import 전 기본 카테고리 태그로 보고 제거할지 확인합니다.

---

### 4.8 무료와이파이

| 항목 | 내용 |
|---|---|
| 저장 대상 | Place |
| PlaceTag seed | 생략 |
| 정제 결과 파일 | `ExData/Cleaned/freewifi_places.json` |
| 스킵 파일 | `ExData/Cleaned/skipped/freewifi_skipped.json` |
| 상태 | Place 정제 완료, PlaceTag 생략 방향 |

무료와이파이는 위치 데이터 자체가 핵심이므로 `Place.category=free_wifi` 기준으로 추천/필터 처리합니다.

---

### 4.9 흡연구역

| 항목 | 내용 |
|---|---|
| 저장 대상 | Place |
| PlaceTag seed | 별도 seed보다 import 로직에서 세부 유형만 조건부 생성 |
| 현재 import 파일 | `backend/recommendations/management/commands/import_smoking_areas.py` |
| 상태 | 세부 유형 태그 import 로직 정리 완료 |

기본 태그인 `흡연구역`, `흡연`, `흡연가능`은 저장하지 않습니다. 원본 데이터에서 명확히 판단 가능한 경우에만 아래 태그를 생성합니다.

```text
실내흡연실
실외흡연구역
부스형흡연구역
개방형흡연구역
```

---

## 5. LFS 관리 대상

대용량 seed 파일과 수집 원본 파일은 Git LFS로 관리합니다.

현재 LFS 관리 대상 예시는 다음과 같습니다.

```text
ExData/JsonData/shelter/*.json
ExData/Cleaned/shelter_places.json
ExData/Cleaned/skipped/shelter_skipped.json
ExData/Cleaned/freewifi_places.json
Test/apiTest/tag/shelterTag/shelter_place_tag_seed.json
Test/apiTest/tag/toiletTag/toilet_place_tag_seed.json
Test/apiTest/tag/parkingTag/parking_place_tag_seed.json
Test/apiTest/tag/parkTag/park_place_tag_seed.json
기타 100MB 초과 seed JSON
```

---

## 6. 보안 및 API 키 주의사항

`.env` 파일에는 API 키가 포함될 수 있으므로 절대 커밋하지 않습니다.

쉼터 API 서비스키는 한 번 로그에 노출된 이력이 있으므로 추후 재발급을 권장합니다. 쉼터 API는 IP 등록 이슈가 있었으므로 다른 환경에서 재수집할 경우 IP 승인 여부를 먼저 확인합니다.

---

## 7. 남은 데이터 작업

다음 작업은 데이터 자체를 새로 많이 만드는 것이 아니라, import 구조로 넘기기 위한 마무리입니다.

1. 정제 데이터 import용 폴더 생성
2. `ExData/Cleaned`, `Test/apiTest/tag` 산출물을 import용 폴더로 복사
3. 주차장 `category_rule` 잔여 태그 의미 확인
4. 쉼터 `무더위쉼터` 태그 최종 제외 여부 확인
5. `ExternalPlaceTag` 모델 추가 후 카페 seed import 준비

추천 import 폴더 구조:

```text
backend/recommendations/fixtures/import_data/
├─ places/
├─ place_tags/
└─ external_place_tags/
```

원본 산출물은 삭제하거나 이동하지 않고, import용 복사본만 생성합니다.

---

## 8. 다음 구현 작업

1. `ExternalPlaceTag` 모델 추가
2. `makemigrations`, `migrate`
3. `import_places.py` 작성
4. `import_place_tags.py` 작성
5. `import_external_place_tags.py` 작성
6. 추천 API에서 생활 인프라는 DB 검색, 카페는 카카오 API + ExternalPlaceTag 매칭 구조로 수정
