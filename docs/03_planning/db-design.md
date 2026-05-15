# DB 설계서

## 1. 설계 목적

본 문서는 상황 기반 생활 장소 추천 지도 서비스의 데이터베이스 구조를 정의한다.

본 서비스는 외부 데이터 기반 장소 정보를 저장하고, 장소별 카테고리와 태그를 관리하며, 사용자의 현재 위치와 상황에 맞는 장소 추천 결과를 제공하는 것을 목표로 한다.

초기 구현에서는 복잡한 머신러닝 기반 추천보다 규칙 기반 추천을 우선하며, 장소의 카테고리, 태그, 거리, 최신성, 신뢰도 정보를 추천 점수 계산에 활용한다.

---

## 2. 주요 엔티티

| 엔티티 | 설명 |
|---|---|
| User | 서비스 사용자 정보 |
| Place | 추천 대상 장소 정보 |
| Category | 장소의 큰 분류 정보 |
| Tag | 추천 및 필터링에 사용하는 태그 정보 |
| PlaceTag | 장소와 태그의 연결 정보 및 태그 신뢰도 정보 |
| Bookmark | 사용자가 저장한 장소 정보 |
| Review | 사용자가 작성한 장소 후기 또는 메모 |
| Report | 장소 정보 오류 제보 정보 |
| Verification | 장소 또는 태그 검증 정보 |

---

## 3. 핵심 테이블 설명

### 3.1 User

서비스 사용자의 기본 정보를 저장한다.

초기 구현에서는 Django 기본 User 모델을 활용하고, 필요 시 프로필 정보를 별도 확장한다.

---

### 3.2 Category

장소의 큰 분류를 저장한다.

예시 카테고리는 다음과 같다.

| code | name |
|---|---|
| toilet | 공중화장실 |
| freewifi | 무료 와이파이 |
| citypark | 도시공원 |
| smoking_area | 흡연구역 |
| parking | 주차장 |
| shelter | 쉼터 |

초기 구현에서는 데이터 확보가 가능한 카테고리를 우선 사용한다.

---

### 3.3 Place

추천 대상이 되는 장소 정보를 저장한다.

공공데이터, CSV, JSON, API 등을 통해 확보한 장소 데이터를 공통 구조로 저장한다.

장소 데이터는 출처마다 컬럼이 다르므로, 지도 표시와 추천에 필요한 공통 필드는 별도 컬럼으로 저장하고 나머지 원본 데이터는 `raw_data`에 보관한다.

PlaceTag는 단순히 장소와 태그를 연결하는 테이블이 아니라, 태그의 출처, 상태, 신뢰도, 검증 여부, 근거 정보를 관리하는 핵심 테이블이다.

지도 API에서 실시간으로 가져온 장소는 기본적으로 Place에 저장하지 않으며, 사용자가 저장하거나 검증 대상이 된 경우에만 Place로 저장한다.

---

### 3.4 Tag

추천과 필터링에 사용할 태그 정보를 저장한다.

예시 태그는 다음과 같다.

| tag_type | 예시 |
|---|---|
| facility | 화장실, 와이파이, 주차가능, 비상벨 |
| purpose | 산책, 휴식, 작업보조, 흡연 |
| condition | 무료, 24시간, 야외, 실내 |
| accessibility | 장애인편의, 어린이이용 |
| mood | 힐링, 잠깐쉬기 |

---

### 3.5 PlaceTag

장소와 태그의 연결 정보를 저장한다.

본 프로젝트에서는 장소와 태그의 관계를 단순 ManyToMany로 처리하지 않고, 중간 테이블인 PlaceTag를 별도로 관리한다.

그 이유는 같은 태그라도 태그가 붙은 근거와 신뢰도가 다를 수 있기 때문이다.

예를 들어 `와이파이` 태그는 아래처럼 서로 다른 출처를 가질 수 있다.

| 장소 | 태그 | 출처 | 신뢰도 |
|---|---|---|---:|
| 공공 와이파이 지점 | 와이파이 | category_rule | 100 |
| 도서관 근처 장소 | 와이파이 | keyword_rule | 60 |
| 관리자 확인 장소 | 와이파이 | admin_verified | 100 |

따라서 PlaceTag에는 태그 출처, 신뢰도, 검증 여부, 근거를 함께 저장한다.

---

## 4. 테이블 명세

## 4.1 Category

| 컬럼명 | 타입 | NULL | 설명 | 비고 |
|---|---|---|---|---|
| id | bigint | N | 카테고리 ID | PK |
| name | varchar(100) | N | 카테고리명 | 예: 공중화장실 |
| code | varchar(50) | N | 카테고리 코드 | unique |
| description | text | Y | 카테고리 설명 |  |
| is_active | boolean | N | 사용 여부 | 기본값 true |
| created_at | datetime | N | 생성일 |  |
| updated_at | datetime | N | 수정일 |  |

---

## 4.2 Place

| 컬럼명 | 타입 | NULL | 설명 | 비고 |
|---|---|---|---|---|
| id | bigint | N | 장소 ID | PK |
| category_id | bigint | N | 카테고리 ID | FK |
| name | varchar(255) | N | 장소명 |  |
| address | varchar(500) | Y | 지번 주소 |  |
| road_address | varchar(500) | Y | 도로명 주소 |  |
| latitude | decimal(10,7) | N | 위도 | 지도 표시용 |
| longitude | decimal(10,7) | N | 경도 | 지도 표시용 |
| source_name | varchar(255) | Y | 데이터 제공 기관명 |  |
| source_type | varchar(50) | Y | 데이터 출처 유형 | public_data, api, csv 등 |
| source_file | varchar(255) | Y | 원본 파일명 |  |
| source_row_id | varchar(100) | Y | 원본 행 식별값 |  |
| data_base_date | date | Y | 데이터 기준일 |  |
| raw_data | json | Y | 원본 행 데이터 | JSONField |
| is_active | boolean | N | 서비스 노출 여부 | 기본값 true |
| created_at | datetime | N | 생성일 |  |
| updated_at | datetime | N | 수정일 |  |

---

## 4.3 Tag

| 컬럼명 | 타입 | NULL | 설명 | 비고 |
|---|---|---|---|---|
| id | bigint | N | 태그 ID | PK |
| name | varchar(100) | N | 태그명 | 예: 와이파이 |
| code | varchar(50) | N | 태그 코드 | unique |
| tag_type | varchar(30) | N | 태그 유형 | facility, purpose 등 |
| description | text | Y | 태그 설명 |  |
| is_active | boolean | N | 사용 여부 | 기본값 true |
| created_at | datetime | N | 생성일 |  |
| updated_at | datetime | N | 수정일 |  |

---

## 4.4 PlaceTag

| 컬럼명 | 타입 | NULL | 설명 | 비고 |
|---|---|---|---|---|
| id | bigint | N | 장소 태그 ID | PK |
| place_id | bigint | N | 장소 ID | FK |
| tag_id | bigint | N | 태그 ID | FK |
| source | varchar(30) | N | 태그 부여 출처 | category_rule, field_rule 등 |
| confidence | smallint | N | 태그 신뢰도 | 0~100 |
| is_verified | boolean | N | 검증 여부 | 기본값 false |
| rule_name | varchar(100) | Y | 적용된 규칙명 |  |
| evidence | text | Y | 태그 부여 근거 |  |
| created_at | datetime | N | 생성일 |  |
| verified_at | datetime | Y | 검증일 |  |

---

## 4.5 Bookmark

| 컬럼명 | 타입 | NULL | 설명 | 비고 |
|---|---|---|---|---|
| id | bigint | N | 북마크 ID | PK |
| user_id | bigint | N | 사용자 ID | FK |
| place_id | bigint | N | 장소 ID | FK |
| created_at | datetime | N | 저장일 |  |

---

## 4.6 Review

| 컬럼명 | 타입 | NULL | 설명 | 비고 |
|---|---|---|---|---|
| id | bigint | N | 후기 ID | PK |
| user_id | bigint | N | 사용자 ID | FK |
| place_id | bigint | N | 장소 ID | FK |
| content | text | N | 후기 또는 메모 내용 |  |
| rating | smallint | Y | 평점 | 선택 기능 |
| created_at | datetime | N | 작성일 |  |
| updated_at | datetime | N | 수정일 |  |

---

## 4.7 Report

| 컬럼명 | 타입 | NULL | 설명 | 비고 |
|---|---|---|---|---|
| id | bigint | N | 오류 제보 ID | PK |
| user_id | bigint | Y | 사용자 ID | FK, 비회원 제보 가능 시 nullable |
| place_id | bigint | N | 장소 ID | FK |
| report_type | varchar(50) | N | 제보 유형 | 위치 오류, 폐쇄, 정보 오류 등 |
| content | text | Y | 제보 내용 |  |
| status | varchar(30) | N | 처리 상태 | pending, approved, rejected |
| created_at | datetime | N | 제보일 |  |
| updated_at | datetime | N | 수정일 |  |

---

## 4.8 Verification

| 컬럼명 | 타입 | NULL | 설명 | 비고 |
|---|---|---|---|---|
| id | bigint | N | 검증 ID | PK |
| user_id | bigint | Y | 검증 사용자 ID | FK |
| place_id | bigint | N | 장소 ID | FK |
| place_tag_id | bigint | Y | 장소 태그 ID | FK |
| verification_type | varchar(50) | N | 검증 유형 | place, tag |
| result | varchar(30) | N | 검증 결과 | valid, invalid |
| comment | text | Y | 검증 의견 |  |
| created_at | datetime | N | 검증일 |  |

---

## 5. 주요 관계

| 관계 | 설명 |
|---|---|
| Category 1 : N Place | 하나의 카테고리는 여러 장소를 가진다. |
| Place 1 : N PlaceTag | 하나의 장소는 여러 태그 연결 정보를 가진다. |
| Tag 1 : N PlaceTag | 하나의 태그는 여러 장소에 연결될 수 있다. |
| User 1 : N Bookmark | 하나의 사용자는 여러 장소를 저장할 수 있다. |
| Place 1 : N Bookmark | 하나의 장소는 여러 사용자에게 저장될 수 있다. |
| User 1 : N Review | 하나의 사용자는 여러 후기를 작성할 수 있다. |
| Place 1 : N Review | 하나의 장소에는 여러 후기가 작성될 수 있다. |
| Place 1 : N Report | 하나의 장소에는 여러 오류 제보가 등록될 수 있다. |
| Place 1 : N Verification | 하나의 장소에는 여러 검증 기록이 등록될 수 있다. |

---

## 6. 설계 판단 근거

- 외부 데이터는 출처마다 컬럼 구조가 다르므로, 공통 필드와 원본 데이터를 분리하여 저장한다.
- 지도 표시와 거리 계산을 위해 위도와 경도는 Place의 필수 필드로 관리한다.
- 장소와 태그는 다대다 관계이지만, 태그 출처와 신뢰도 관리가 필요하므로 PlaceTag를 별도 엔티티로 설계한다.
- 초기 추천 로직은 카테고리, 태그, 거리, 최신성, 신뢰도를 활용한 규칙 기반 추천으로 구현한다.
- 사용자 제보와 검증은 초기 데이터 확보 수단이 아니라, 서비스 운영 중 정보 보완 및 신뢰도 개선 기능으로 사용한다.

---

## 7. 초기 구현 범위

초기 구현에서는 다음 테이블을 우선 구현한다.

| 우선순위 | 테이블 |
|---|---|
| 1 | Category |
| 1 | Place |
| 1 | Tag |
| 1 | PlaceTag |
| 2 | Bookmark |
| 2 | Report |
| 3 | Review |
| 3 | Verification |

초기 핵심 기능은 장소 데이터 표시, 카테고리 필터, 태그 필터, 추천 결과 목록, 지도 마커 표시이다.