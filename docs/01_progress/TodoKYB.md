# KYB 진행 상황 요약

## 1. 현재 프로젝트 방향

상황 기반 생활 장소 추천 지도 서비스는 단순 지도 검색이 아니라, 사용자의 위치와 상황에 맞는 생활 장소를 추천하고 추천 결과를 지도에서 확인하는 서비스입니다.

초기 추천은 머신러닝보다 규칙 기반으로 구현합니다.

```text
추천 기준 = 카테고리 + 태그 + 거리 + 최신성 + 신뢰도 + 확인 필요 감점
```

---

## 2. 오늘까지 정리된 내용

### 2.1 태그 저장 원칙 정리

- `Place.category`만으로 알 수 있는 기본 태그는 `PlaceTag`에 저장하지 않음
- 추천/필터에 실제로 쓸 세부 속성 태그만 저장
- DB에는 source를 세분화해서 저장하고, 화면/API에서는 display_group으로 묶어서 출력
- 블로그/AI/키워드 기반 태그는 확정 정보가 아니라 후보 정보로 관리

---

### 2.2 데이터 seed 작업 상태

| 데이터 | 상태 |
|---|---|
| 카페 | ExternalPlaceTag용 seed 생성 완료 |
| 관광지 | PlaceTag seed 생성 완료 |
| 도시공원 | PlaceTag seed 생성 완료, 기본 태그 제거 기록 있음 |
| 해수욕장 | PlaceTag seed 생성 완료, 좌표 없는 1건 스킵 |
| 주차장 | PlaceTag seed 생성 완료, 기본 `주차장` 제거. category_rule 잔여 확인 필요 |
| 공중화장실 | PlaceTag seed 생성 완료, 기본/노이즈 태그 제거 완료 |
| 쉼터 | PlaceTag seed 생성 완료, `무더위쉼터` 제외 여부 확인 필요 |
| 무료와이파이 | Place 정제 완료, PlaceTag seed 생략 방향 |
| 흡연구역 | 세부 유형 태그 import 로직 정리 완료 |

---

### 2.3 모델 상태

- `Place`, `Tag`, `PlaceTag` 모델은 현재 사용 중
- `PlaceTag.source` choices에 `field_rule`, `keyword_rule`, `blog_search`, `external_api`, `external_data`, `ai_suggested`, `checked`, `user_verified`, `warning_tags` 반영됨
- `ExternalPlaceTag` 모델은 아직 없음
- 카페 seed를 사용하려면 `ExternalPlaceTag` 모델 추가 필요

---

### 2.4 문서 최신화

다음 문서를 현재 기준으로 최신화했습니다.

```text
docs/04_recommendation/tagging-rule.md
docs/02_data/data-cleaning-policy.md
docs/03_planning/db-design.md
docs/02_data/tag-seed-summary.md
docs/01_progress/TodoKYB.md
```

---

## 3. 다음에 이어서 할 작업

다음에 “이어서 하자”라고 하면 아래 순서로 진행합니다.

```text
1. 정제 데이터 import용 폴더 생성
2. 정제된 places / place_tags / external_place_tags 파일을 한 폴더로 복사
3. 주차장 category_rule 잔여 태그 확인
4. 쉼터 무더위쉼터 태그 제외 여부 확인
5. ExternalPlaceTag 모델 추가
6. makemigrations / migrate
7. import_places.py 작성
8. import_place_tags.py 작성
9. import_external_place_tags.py 작성
10. 추천 API 수정
11. 팀원이 작업한 프론트 변경사항 확인 후 API 응답 구조와 맞추기
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
- 카카오/네이버/구글 지도 리뷰를 무단 크롤링해서 저장하지 않음
- AI는 실제 장소 정보를 생성하지 않고, 확보된 데이터의 태그 후보 생성/추천 이유 생성 보조로만 사용
