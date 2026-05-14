# ERD 설계

## 1. ERD 목적

본 문서는 상황 기반 생활 장소 추천 지도 서비스의 주요 데이터 구조와 테이블 간 관계를 정의한다.

서비스의 핵심 데이터는 장소, 카테고리, 태그이며, 장소와 태그의 관계를 통해 상황 기반 추천을 제공한다.

---

## 2. 주요 엔티티

| 엔티티 | 설명 |
|---|---|
| User | 서비스 사용자 |
| Category | 장소 카테고리 |
| Place | 추천 대상 장소 |
| Tag | 추천 및 필터링 태그 |
| PlaceTag | 장소와 태그의 연결 및 신뢰도 정보 |
| Bookmark | 사용자 저장 장소 |
| Review | 장소 후기 또는 메모 |
| Report | 장소 정보 오류 제보 |
| Verification | 장소 또는 태그 검증 기록 |

---

## 3. 핵심 관계 요약

```txt
User 1 : N Bookmark
User 1 : N Review
User 1 : N Report
User 1 : N Verification

Category 1 : N Place

Place 1 : N PlaceTag
Tag 1 : N PlaceTag

Place 1 : N Bookmark
Place 1 : N Review
Place 1 : N Report
Place 1 : N Verification

PlaceTag 1 : N Verification
```

## 4. ERD 설계 판단

### 4.1 Place와 Category

하나의 장소는 하나의 대표 카테고리를 가진다.

예를 들어 공중화장실 데이터에서 수집된 장소는 `공중화장실` 카테고리를 가진다.

```txt
Category 1 : N Place
```

---

### 4.2 Place와 Tag

하나의 장소는 여러 태그를 가질 수 있고, 하나의 태그는 여러 장소에 연결될 수 있다.

하지만 태그의 출처, 신뢰도, 검증 여부를 함께 저장해야 하므로 단순 ManyToMany 대신 `PlaceTag`를 사용한다.

```txt
Place 1 : N PlaceTag
Tag 1 : N PlaceTag
```

---

### 4.3 PlaceTag 설계 이유

같은 태그라도 부여 근거가 다를 수 있다.

예시:

| 장소 | 태그 | source | confidence |
|---|---|---|---:|
| 무료 와이파이 지점 | 와이파이 | category_rule | 100 |
| 도서관 주변 장소 | 작업가능후보 | keyword_rule | 70 |
| 관리자 확인 장소 | 와이파이 | admin_verified | 100 |

따라서 PlaceTag는 추천 점수 계산과 정보 신뢰도 표시를 위한 핵심 테이블이다.

---

## 5. 초기 구현 ERD 범위

초기 구현에서는 다음 테이블을 우선 구현한다.

```txt
Category
Place
Tag
PlaceTag
```

이후 여유가 있을 경우 다음 테이블을 추가한다.

```txt
Bookmark
Report
Review
Verification
```