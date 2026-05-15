## 해당 파일은 개인의 할 일을 잊지 않기 위해서 정리해둔 파일로 내용은 계속적으로 수정될 예정


---

# 상황 기반 장소 추천 서비스 진행 순서

## 0단계. 서비스 기준 재확정

먼저 팀 안에서 이 기준을 고정해야 합니다.

```text
이 서비스의 핵심은 지도 검색이 아니다.
지도 API는 장소 후보 수집과 지도 표시를 위한 보조 수단이다.

서비스의 핵심은 장소별 추천 가치 태그를 확보하고,
태그의 출처, 상태, 검증 여부, 신뢰도를 관리한 뒤,
사용자의 상황에 맞는 장소를 추천하는 것이다.
```

이 기준이 있어야 이후 작업이 흔들리지 않습니다.

---

# 1단계. 추천 가치 태그 확정

가장 먼저 태그부터 정리해야 합니다.

여기서 중요한 건 태그를 한 덩어리로 보지 않는 것입니다.

## 1-1. 태그 역할 분리

```text
카테고리 태그
- 카페, 공원, 흡연구역, 화장실, 주차장 등
- 장소 분류와 필터용

추천 가치 태그
- 혼자 이용 좋음
- 오래 머물기 좋음
- 조용함
- 노트북 작업 가능
- 콘센트 있음
- 와이파이 있음
- 분위기 좋음
- 산책하기 좋음
- 야경 보기 좋음
- 추천 품질의 핵심

상태/주의 태그
- 좌석 확인 필요
- 콘센트 확인 필요
- 운영 정보 확인 필요
- 위치 확인 필요
- 테이크아웃 가능성
- 감점 또는 안내용
```

## 1-2. 태그 상태 정의

태그는 붙었다고 끝이 아니라 상태가 있어야 합니다.

```text
confirmed
- 확인 근거가 있는 태그
- 추천 점수에 강하게 반영

candidate
- 가능성은 있지만 확정되지 않은 태그
- 약하게 반영

needs_verification
- 확인이 필요한 태그
- 안내 또는 감점

rejected
- 확인 결과 맞지 않은 태그
- 추천 제외 또는 강한 감점
```

## 1-3. 태그 출처 정의

```text
category_rule
- 카테고리 기반 자동 부여

runtime_rule
- 지도 API 검색 결과에 추천 시점에만 붙이는 임시 태그

external_data
- 공공데이터 원본 필드에서 확인 가능한 태그

ai_suggested
- AI가 제안한 후보 태그

team_checked
- 팀이 직접 확인한 태그

admin_checked
- 관리자 또는 팀 검수 태그

user_verified
- 사용자 검증 기반 태그
```

이 단계 산출물:

```text
docs/04_recommendation/recommendation-tag-strategy.md
docs/04_recommendation/tag-mapping-policy.md
```

---

# 2단계. 데이터 소스 목록 확정

그다음 데이터입니다.

지금은 “데이터가 있냐 없냐”가 아니라, **어떤 추천 태그를 만들 수 있는 데이터냐**를 기준으로 봐야 합니다.

## 2-1. 데이터 후보 구분

```text
자체/공공데이터 기반
- 흡연구역
- 공중화장실
- 공공와이파이
- 도시공원
- 주차장
- 쉼터

지도 API 기반 후보
- 카페
- 음식점
- 관광지
- 산책/힐링 후보
- 드라이브 목적지 후보

직접 확인 데이터
- 팀이 확인한 카페
- 팀이 확인한 쉬기 좋은 장소
- 팀이 확인한 작업 가능 장소
```

## 2-2. 데이터별 확인 항목

각 데이터마다 아래를 확인해야 합니다.

```text
데이터명
제공처
제공 방식
좌표 제공 여부
주소 제공 여부
세부 위치 제공 여부
갱신일 또는 기준일
사용 조건
원본 필드 목록
추천 가치 태그로 변환 가능한 필드
정제 난이도
사용 우선순위
```

이 단계 산출물:

```text
docs/02_data/data-source-status.md
```

---

# 3단계. 공통 장소 스키마 확정

데이터를 여러 개 모으면 필드가 전부 다릅니다.
그래서 먼저 공통 구조를 정해야 합니다.

## 3-1. 공통 Place 구조

모든 정제 데이터는 최종적으로 이 구조에 맞춥니다.

```json
{
  "external_id": "source_0001",
  "name": "장소명",
  "category": "cafe",
  "address": "주소",
  "lat": 35.12345,
  "lng": 129.12345,
  "detail_location": "건물 1층 외부",
  "source": "data_source_key",
  "source_name": "데이터 출처명",
  "source_updated_at": "2026-05-15",
  "data_quality_status": "usable",
  "data_quality_score": 80,
  "default_tags": [],
  "candidate_tags": [],
  "warning_tags": [],
  "raw": {}
}
```

## 3-2. 품질 상태 기준

```text
usable
- 좌표 있음
- 장소명 있음
- 카테고리 명확
- 추천에 바로 사용 가능

candidate
- 기본 정보는 있으나 일부 정보 부족
- 후보로 사용 가능

needs_review
- 위치나 정보가 모호함
- 검토 필요

excluded
- 추천에 사용하기 어려움
```

이 단계 산출물:

```text
docs/02_data/common-place-schema.md
docs/02_data/data-cleaning-policy.md
```

---

# 4단계. 데이터 정제 기준 작성

이제 데이터별로 정제 기준을 만듭니다.

## 4-1. 흡연구역 정제 기준

예를 들면:

```text
세부 위치 + 좌표 있음
→ usable
→ 세부 위치 있음, 좌표 확인

좌표는 있으나 건물명만 있음
→ candidate
→ 위치 확인 필요

좌표 없음
→ needs_review 또는 excluded

설치 위치가 모호함
→ needs_review
```

## 4-2. 카페 후보 정제 기준

카페는 지도 API 검색 결과를 그대로 추천하면 안 됩니다.

```text
저가형/테이크아웃 가능성이 높은 브랜드
→ 감점 또는 주의 태그

좌석 여부 확인 불가
→ 좌석 확인 필요

콘센트/와이파이 확인 불가
→ 콘센트 확인 필요, 와이파이 확인 필요

팀 확인 장소
→ confirmed 태그 부여 가능
```

## 4-3. 공공데이터 정제 기준

```text
공중화장실
- 장애인화장실 여부
- 운영시간
- 남녀구분
- 좌표/주소

공공와이파이
- 설치 위치
- 제공 기관
- 실내/실외 추정 가능 여부

도시공원
- 공원 구분
- 면적
- 시설 정보
- 산책/휴식 후보 여부
```

이 단계 산출물:

```text
docs/02_data/data-cleaning-policy.md
docs/02_data/tag-mapping-policy.md
```

---

# 5단계. 실제 데이터 수집

여기서부터 실제 데이터를 모읍니다.

## 5-1. 원본 데이터 저장

원본은 그대로 보존합니다.

```text
data/raw/
```

예시:

```text
data/raw/smoking_area/
data/raw/public_toilet/
data/raw/public_wifi/
data/raw/parks/
data/raw/parking/
```

## 5-2. 정제 데이터 생성

정제 후에는 공통 스키마로 저장합니다.

```text
data/normalized/
```

예시:

```text
data/normalized/smoking_area_normalized.json
data/normalized/public_toilet_normalized.json
data/normalized/public_wifi_normalized.json
data/normalized/parks_normalized.json
```

이 단계 산출물:

```text
data/raw/*
data/normalized/*
```

---

# 6단계. 추천 가치 태그 확보

이 단계가 핵심입니다.

공공데이터만으로는 추천 가치 태그가 부족합니다.
따라서 별도 확보 방식이 필요합니다.

## 6-1. 직접 확인 대상 선정

```text
카페 10~20개
쉬기 좋은 장소 5개
산책/힐링 장소 5개
흡연구역 일부 5개
```

## 6-2. 라벨링 기준 작성

예시:

```text
콘센트 있음
- 좌석 근처 사용 가능한 콘센트 확인

와이파이 있음
- 매장 안내 또는 직접 연결 가능 확인

노트북 작업 가능
- 좌석, 테이블, 분위기, 콘센트 등을 종합해 확인

조용함
- 방문 시 집중 가능한 소음 수준

오래 머물기 좋음
- 좌석, 공간, 분위기가 장시간 체류에 적합

혼자 이용 좋음
- 1인 좌석 또는 혼자 앉기 부담 없는 구조
```

## 6-3. 라벨링 데이터 작성

```text
data/verified/
```

예시:

```text
data/verified/checked_cafes.csv
data/verified/checked_places.json
```

이 단계 산출물:

```text
docs/04_recommendation/tag-labeling-guide.md
data/verified/*
```

---

# 7단계. DB 설계 확정

데이터와 태그 기준이 정리된 뒤 DB 모델을 확정합니다.

## 7-1. 핵심 모델

```text
Place
- 장소 기본 정보

Category
- 장소 카테고리

Tag
- 태그 사전

PlaceTag
- 장소와 태그 연결
- 출처, 상태, 신뢰도, 근거 관리
```

## 7-2. PlaceTag 핵심 필드

```text
place
tag
source
status
confidence
evidence
is_verified
verified_at
created_at
```

이 단계 산출물:

```text
docs/03_planning/db-design.md
docs/03_planning/erd.md
```

그다음에야 Django 모델을 만듭니다.

---

# 8단계. 데이터 import 구조 구현

정제 데이터가 준비되면 DB에 넣습니다.

## 8-1. import 대상

```text
data/normalized/*
data/verified/*
```

## 8-2. import 결과

```text
Place 생성
Tag 생성
PlaceTag 생성
```

## 8-3. 중복 기준

```text
source + external_id
```

카카오 API 저장 장소는:

```text
source = kakao_local
external_id = kakao place id
```

공공데이터는:

```text
source = public_toilet_data
external_id = 원본 관리번호 또는 직접 생성 ID
```

이 단계 산출물:

```text
Django models
management command
seed/import script
```

---

# 9단계. 추천 로직 설계

이제 추천 로직입니다.
이전처럼 먼저 짜면 안 됩니다. 데이터와 태그 구조가 잡힌 뒤에 해야 합니다.

## 9-1. 추천 입력

```text
사용자 위치
사용자 상황
선택 카테고리
자연어 입력
```

## 9-2. 상황 → 태그 조건 변환

예시:

```text
“조용히 노트북 작업할 곳”
→ 조용함
→ 노트북 작업 가능
→ 콘센트 있음
→ 와이파이 있음
→ 오래 머물기 좋음
```

## 9-3. 추천 점수

```text
추천 점수 =
거리 점수
+ 카테고리 일치 점수
+ confirmed 태그 일치 점수
+ candidate 태그 일치 점수
+ 데이터 품질 점수
+ 신뢰도 점수
- warning 태그 감점
```

## 9-4. 결과 우선순위

```text
1. 검증 태그가 있는 DB 장소
2. 후보 태그가 있는 DB 장소
3. 자체 수집 데이터 기반 장소
4. 지도 API 기반 임시 후보 장소
```

이 단계 산출물:

```text
docs/04_recommendation/recommendation-logic.md
```

---

# 10단계. AI 활용 구조 설계

AI는 여기서 들어갑니다.

## 10-1. AI 역할

```text
자연어 입력을 추천 태그 조건으로 변환
장소 설명/확인 메모를 후보 태그로 변환
추천 이유 생성
```

## 10-2. AI가 하면 안 되는 것

```text
실제 장소 정보 생성
검증되지 않은 시설 여부 확정
운영 여부 단정
```

## 10-3. AI 태그 저장

```text
source = ai_suggested
status = candidate
confidence = 낮음~중간
```

이 단계 산출물:

```text
docs/04_recommendation/ai-tag-policy.md
```

---

# 11단계. 백엔드 API 구현

이제 API입니다.

## 11-1. 필요한 API

```text
추천 API
GET /api/recommendations/

장소 목록 API
GET /api/places/

장소 상세 API
GET /api/places/{id}/

태그 목록 API
GET /api/tags/

장소 저장 API
POST /api/places/save-from-external/

태그 검증 API
POST /api/place-tags/{id}/verify/
```

## 11-2. 추천 API 흐름

```text
입력 받기
→ 상황/태그 조건 파싱
→ DB 장소 검색
→ 지도 API 후보 검색
→ 점수 계산
→ 추천 이유 생성
→ 응답
```

---

# 12단계. 프론트 화면 구현

백엔드 구조가 잡힌 뒤 화면입니다.

## 12-1. 주요 화면

```text
추천 지도 화면
장소 상세 화면
장소 저장 화면
태그 확인/검증 화면
```

## 12-2. 추천 결과 표시

추천 결과에서 반드시 구분해야 합니다.

```text
검증된 장소
후보 장소
확인 필요 정보
추천 이유
태그 출처
지도 마커
```

---

# 13단계. 문서 정리와 발표 구조

마지막에 문서를 정리합니다.

## 발표 핵심 흐름

```text
1. 기존 지도 검색의 한계
2. 장소 추천에는 상황별 태그가 필요함
3. 태그는 출처와 검증 상태에 따라 신뢰도가 다름
4. 지도 API 결과는 후보로 사용
5. 검증된 DB 장소는 추천 점수에서 우선 반영
6. AI는 태그 후보 생성과 추천 이유 생성에 활용
```

---

# 지금 당장 해야 할 일

현재 위치에서 바로 시작할 작업은 이것입니다.

```text
1. data-source-status.md 확인/보강
2. common-place-schema.md 작성 또는 수정
3. tag-mapping-policy.md 작성 또는 수정
4. 흡연구역 데이터부터 공통 스키마에 맞게 재정제
5. 그다음 공중화장실, 공공와이파이, 공원 데이터 수집
```

즉, 지금은 **코드 구현이 아니라 데이터 정제 체계 확정**부터입니다.

---

# 전체 순서 한 줄 요약

```text
서비스 기준 확정
→ 추천 가치 태그 확정
→ 데이터 소스 조사
→ 공통 장소 스키마 확정
→ 데이터별 정제 기준 작성
→ 실제 데이터 수집
→ 추천 가치 태그 확보
→ DB 설계
→ 데이터 import
→ 추천 로직
→ AI 활용
→ API
→ 화면
→ 문서/발표
```

이 순서로 가야 제대로 진행됩니다.
