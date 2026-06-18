# DB 생성 방식 안내서

## 1. 문서 목적

이 문서는 `kyb` 브랜치 기준으로 정제된 장소 데이터와 태그 seed 데이터를 Django DB에 넣는 방식을 정리합니다.

현재 DB 생성 작업은 완성본이 아니라 진행 중인 상태입니다. 따라서 이 문서는 현재 구현된 import 명령어로 실행 가능한 범위와 아직 추가 구현이 필요한 범위를 구분해서 안내합니다.

---

## 2. 현재 DB 생성 방식 요약

현재 구조는 Django fixture를 그대로 `loaddata` 하는 방식이 아니라, 정제 JSON 파일을 읽어서 `Place`, `Tag`, `PlaceTag` 모델에 맞게 저장하는 custom management command 방식입니다.

주요 모델은 다음과 같습니다.

| 모델 | 역할 |
|---|---|
| `Place` | 장소 기본 정보 저장. 장소명, 카테고리, 주소, 좌표, 출처, 원본 raw 데이터 관리 |
| `Tag` | 추천과 필터에 사용할 태그 이름과 태그 유형 관리 |
| `PlaceTag` | 장소와 태그의 연결 정보 관리. 태그 출처, 상태, 신뢰도, 근거, 검증 여부를 함께 저장 |

`Place`는 `source + external_id` 조합으로 중복 저장을 방지합니다.

`PlaceTag`는 `place + tag + source` 조합으로 중복 저장을 방지합니다.

---

## 3. 현재 파일 구조

현재 DB import용 파일은 아래 위치를 기준으로 둡니다.

```text
backend/recommendations/fixtures/
├─ places/
│  ├─ beach_db_ready.json
│  ├─ citypark_db_ready.json
│  ├─ freewifi_db_ready.json
│  ├─ parking_db_ready.json
│  ├─ shelter_db_ready.json
│  ├─ smoking_places_merged_deduplicated.json
│  ├─ toilet_db_ready.json
│  └─ tourism_db_ready.json
│
├─ tags/
│  ├─ beach_place_tag_seed.json
│  ├─ cafe_external_place_tags_seed.json
│  ├─ park_place_tag_seed.json
│  ├─ parking_place_tag_seed.json
│  ├─ shelter_place_tag_seed.json
│  ├─ toilet_place_tag_seed.json
│  └─ tourist_spot_busan_place_tag_seed.json
│
└─ review/
   └─ smoking/
      ├─ smoking_geocode_failed.json
      ├─ smoking_geocode_success.json
      ├─ smoking_places_merged_deduplicated.before_geocode.json
      └─ smoking_places_merged_deduplicated.geocoded_preview.json
```

주의할 점은 파일이 존재한다고 해서 모두 import 명령어에 연결된 것은 아니라는 점입니다. 현재 import 명령어가 실제로 처리하는 범위는 아래에서 별도로 정리합니다.

---

## 4. 실행 전 준비

### 4.1 브랜치 이동

```bash
git fetch origin
git checkout kyb
git pull origin kyb
```

현재 `kyb` 브랜치는 `master`와 차이가 있으므로, 팀 작업 상황에 따라 merge 또는 rebase 여부를 먼저 확인합니다.

### 4.2 Git LFS 파일 받기

대용량 JSON 파일은 Git LFS 포인터 파일일 수 있습니다. 실제 JSON이 아니라 LFS 포인터 파일이면 import 명령어에서 에러가 발생합니다.

```bash
git lfs install
git lfs pull
```

에러 예시:

```text
Git LFS 실제 파일이 아니라 포인터 파일입니다.
git lfs pull 실행 후 다시 시도해 주세요.
```

### 4.3 백엔드 의존성 설치

```bash
cd backend
python -m venv venv
source venv/Scripts/activate   # Git Bash / Windows 기준
pip install -r requirements.txt
```

PowerShell을 사용하는 경우 가상환경 활성화 명령은 다음처럼 사용할 수 있습니다.

```powershell
.\venv\Scripts\Activate.ps1
```

### 4.4 마이그레이션 실행

```bash
python manage.py makemigrations
python manage.py migrate
```

이미 마이그레이션 파일이 최신이라면 `makemigrations`에서 변경 없음으로 나올 수 있습니다.

---

## 5. Place 데이터 import

### 5.1 현재 구현된 명령어

장소 데이터 import 명령어는 다음 파일에 있습니다.

```text
backend/recommendations/management/commands/import_fixture_places.py
```

명령어 실행 형식은 다음과 같습니다.

```bash
python manage.py import_fixture_places --only all
```

테스트만 하고 DB에 저장하지 않으려면 `--dry-run`을 붙입니다.

```bash
python manage.py import_fixture_places --only all --dry-run
```

일부 개수만 테스트하려면 `--limit`을 사용합니다.

```bash
python manage.py import_fixture_places --only toilet --limit 100 --dry-run
```

### 5.2 현재 import 가능한 Place 범위

현재 `import_fixture_places.py`의 설정에 등록된 카테고리는 다음 5개입니다.

| key | 파일 | category 기본값 | source 기본값 | 현재 상태 |
|---|---|---|---|---|
| `beach` | `beach_db_ready.json` | `beach` | `beach` | import 가능 |
| `freewifi` | `freewifi_db_ready.json` | `freewifi` | `freewifi` | import 가능 |
| `shelter` | `shelter_db_ready.json` | `shelter` | `shelter` | import 가능 |
| `toilet` | `toilet_db_ready.json` | `toilet` | `toilet` | import 가능 |
| `smoking` | `smoking_places_merged_deduplicated.json` | `smoking_area` | `smokearea_kr_supabase` | import 가능 |

아래 파일은 `fixtures/places`에는 있지만 현재 명령어 설정에는 아직 등록되어 있지 않습니다.

| 파일 | 현재 상태 | 다음 작업 |
|---|---|---|
| `citypark_db_ready.json` | 파일 있음, import 설정 미등록 | `PLACE_FILE_CONFIGS`에 `citypark` 추가 필요 |
| `parking_db_ready.json` | 파일 있음, import 설정 미등록 | `PLACE_FILE_CONFIGS`에 `parking` 추가 필요 |
| `tourism_db_ready.json` | 파일 있음, import 설정 미등록 | `PLACE_FILE_CONFIGS`에 `tourism` 추가 필요 |

따라서 현재 기준으로 `--only all`을 실행해도 위 3개 파일은 저장되지 않습니다.

### 5.3 카테고리별 실행 예시

```bash
python manage.py import_fixture_places --only beach --dry-run
python manage.py import_fixture_places --only freewifi --dry-run
python manage.py import_fixture_places --only shelter --dry-run
python manage.py import_fixture_places --only toilet --dry-run
python manage.py import_fixture_places --only smoking --dry-run
```

문제가 없으면 `--dry-run`을 제거하고 실행합니다.

```bash
python manage.py import_fixture_places --only beach freewifi shelter toilet smoking
```

### 5.4 저장 방식

명령어는 각 row를 읽어서 `Place.objects.update_or_create()`로 저장합니다.

기준 키는 다음과 같습니다.

```text
source + external_id
```

동일한 `source + external_id`가 이미 있으면 기존 Place를 수정하고, 없으면 새로 생성합니다.

저장되는 주요 필드는 다음과 같습니다.

| 필드 | 내용 |
|---|---|
| `name` | 장소명 |
| `category` | 장소 카테고리 |
| `address` | 주소 |
| `lat` | 위도 |
| `lng` | 경도 |
| `source` | 데이터 출처 구분값 |
| `external_id` | 외부 데이터 ID 또는 생성 ID |
| `source_name` | 출처 표시명 |
| `source_updated_at` | 원본 데이터 기준일 또는 갱신일 |
| `detail_location` | 상세 위치 |
| `data_quality_status` | 데이터 품질 상태 |
| `data_quality_score` | 데이터 품질 점수 |
| `raw` | 원본 row 전체 또는 원본 raw 데이터 |

장소명과 좌표가 없으면 저장 대상에서 제외됩니다.

---

## 6. 흡연구역 세부 태그 처리

흡연구역은 Place import 과정에서 일부 세부 태그를 같이 생성합니다.

기본 태그인 아래 값들은 저장하지 않는 방향입니다.

```text
흡연구역
흡연
흡연가능
흡연장소
생활편의
```

대신 원본 데이터에서 세부 유형을 판단할 수 있을 때만 아래 태그를 생성합니다.

```text
실내흡연실
실외흡연구역
부스형흡연구역
개방형흡연구역
```

기존에 잘못 저장된 흡연구역 기본 태그를 삭제하려면 다음 옵션을 사용할 수 있습니다.

```bash
python manage.py import_fixture_places --only smoking --cleanup-basic-smoking-tags
```

먼저 확인만 하려면 `--dry-run`을 사용합니다. 단, `--cleanup-basic-smoking-tags`는 `--dry-run` 상태에서는 실제 삭제하지 않습니다.

```bash
python manage.py import_fixture_places --only smoking --cleanup-basic-smoking-tags --dry-run
```

---

## 7. 태그 데이터 import

### 7.1 현재 상태 요약

현재 `fixtures/tags` 폴더에는 여러 카테고리의 태그 seed 파일이 있습니다.

하지만 공통 PlaceTag import 명령어인 아래 파일은 아직 비어 있습니다.

```text
backend/recommendations/management/commands/import_fixture_place_tags.py
```

따라서 현재 기준으로는 `beach`, `park`, `parking`, `shelter`, `toilet`, `tourist_spot_busan` 태그 seed를 한 번에 DB에 넣는 공통 명령어는 아직 완성되지 않았습니다.

### 7.2 현재 실행 가능한 태그 관련 명령어

현재 구현된 태그 관련 명령어는 카페 태그용입니다.

```text
backend/recommendations/management/commands/import_cafe_place_tags.py
```

실행 예시는 다음과 같습니다.

```bash
python manage.py import_cafe_place_tags --dry-run
```

일부만 테스트할 경우 다음처럼 실행합니다.

```bash
python manage.py import_cafe_place_tags --limit 100 --dry-run
```

신뢰도 기준을 적용하려면 `--min-confidence`를 사용합니다.

```bash
python manage.py import_cafe_place_tags --min-confidence 70 --dry-run
```

문제가 없으면 `--dry-run`을 제거하고 실행합니다.

```bash
python manage.py import_cafe_place_tags --min-confidence 70
```

### 7.3 카페 태그 저장 방식

카페 태그 명령어는 아래 파일을 읽습니다.

```text
backend/recommendations/fixtures/tags/cafe_external_place_tags_seed.json
```

이 명령어는 row를 장소 단위로 묶은 뒤 `Place`, `Tag`, `PlaceTag`를 저장합니다.

현재 카페 데이터는 카카오 로컬 API 장소 후보와 블로그 검색 기반 태그 후보를 결합한 데이터입니다. 따라서 태그는 확정 정보가 아니라 후보 정보로 보고 `candidate` 중심으로 다룹니다.

카페 Place의 `raw`에는 다음과 같은 메타 정보가 들어갑니다.

| raw 필드 | 의미 |
|---|---|
| `source_type` | `cafe_external_place_tags_seed` |
| `external_source` | 외부 장소 출처 |
| `external_id` | 외부 장소 ID |
| `place_url` | 외부 장소 URL |
| `area_name` | 수집 지역명 |
| `source_query` | 수집 검색어 |
| `blog_evidence_count` | 블로그 근거 수 |
| `suggested_tags` | 추천 후보 태그 |
| `display_tags` | 화면 표시 후보 태그 |
| `warning_tags` | 주의 또는 확인 필요 태그 |
| `tag_details` | 태그별 상세 row |
| `data_note` | 데이터 한계 설명 |

카페 데이터 품질 점수는 다음 요소를 조합해서 계산합니다.

```text
기본 50점
+ 최대 confidence 반영
+ 블로그 근거 수 반영
+ 태그 수 반영
- warning 태그 수 감점
```

점수가 60점 미만이면 `data_quality_status`를 `needs_review`로 저장합니다.

---

## 8. 권장 실행 순서

현재 구현 기준으로는 아래 순서를 권장합니다.

```bash
# 1. 브랜치와 LFS 파일 확인
git fetch origin
git checkout kyb
git pull origin kyb
git lfs pull

# 2. 백엔드로 이동
cd backend

# 3. 의존성 설치
pip install -r requirements.txt

# 4. DB 스키마 반영
python manage.py makemigrations
python manage.py migrate

# 5. Place import 사전 점검
python manage.py import_fixture_places --only all --dry-run

# 6. 구현 완료된 Place import 실행
python manage.py import_fixture_places --only beach freewifi shelter toilet smoking

# 7. 카페 태그 import 사전 점검
python manage.py import_cafe_place_tags --min-confidence 70 --dry-run

# 8. 카페 태그 import 실행
python manage.py import_cafe_place_tags --min-confidence 70
```

처음 실행할 때는 전체 실행보다 `--limit 100 --dry-run`으로 구조를 먼저 확인하는 것을 권장합니다.

---

## 9. 검증용 Django shell 명령

import 후 데이터 개수를 확인합니다.

```bash
python manage.py shell
```

```python
from recommendations.models import Place, Tag, PlaceTag

Place.objects.count()
Tag.objects.count()
PlaceTag.objects.count()

Place.objects.values("category").order_by("category").distinct()
Place.objects.filter(category="smoking_area").count()
PlaceTag.objects.values("source").order_by("source").distinct()
```

카테고리별 개수를 확인하려면 다음처럼 실행합니다.

```python
from django.db.models import Count

Place.objects.values("category").annotate(count=Count("id")).order_by("category")
PlaceTag.objects.values("source", "status").annotate(count=Count("id")).order_by("source", "status")
```

---

## 10. 현재 미완료 작업

현재 `kyb` 브랜치 기준으로 남은 작업은 다음과 같습니다.

### 10.1 Place import 추가 등록

`fixtures/places`에 있으나 아직 `import_fixture_places.py`에 연결되지 않은 파일을 추가해야 합니다.

```text
citypark_db_ready.json
parking_db_ready.json
tourism_db_ready.json
```

추가 위치:

```python
PLACE_FILE_CONFIGS = {
    ...
}
```

추가 시 확인할 사항:

| 확인 항목 | 설명 |
|---|---|
| `filename` | 실제 fixture 파일명과 일치해야 함 |
| `kind` | `db_ready` 또는 `plain_list` 중 구조에 맞게 선택 |
| `default_category` | 서비스에서 사용할 Place.category 값 |
| `default_source` | source 중복 방지용 출처 값 |
| 좌표 키 | 위도/경도 필드가 기존 `LAT_KEYS`, `LNG_KEYS`에 포함되는지 확인 |
| source_updated_at | 기준일 필드가 있는지 확인 |

### 10.2 공통 PlaceTag import 명령어 작성

아래 파일은 현재 비어 있으므로 구현이 필요합니다.

```text
backend/recommendations/management/commands/import_fixture_place_tags.py
```

대상 파일:

```text
beach_place_tag_seed.json
park_place_tag_seed.json
parking_place_tag_seed.json
shelter_place_tag_seed.json
toilet_place_tag_seed.json
tourist_spot_busan_place_tag_seed.json
```

공통 import 명령어는 다음 구조를 권장합니다.

```bash
python manage.py import_fixture_place_tags --only all --dry-run
python manage.py import_fixture_place_tags --only beach toilet tourism --dry-run
```

구현 시 기준 키는 다음처럼 두는 것이 좋습니다.

```text
Place 매칭: source + external_id 우선
대체 매칭: category + name + lat + lng
PlaceTag 중복 방지: place + tag + source
```

### 10.3 카페 데이터 구조 결정

현재 카페 import 명령어는 `Place`, `Tag`, `PlaceTag`에 직접 저장하는 구조입니다.

초기 기획에서는 카페를 지도 API 실시간 검색 결과와 태그 후보를 매칭하는 구조로도 검토했으므로, 최종적으로 아래 둘 중 하나를 정해야 합니다.

| 방식 | 설명 | 장점 | 주의점 |
|---|---|---|---|
| 카페도 `Place`에 저장 | 현재 `import_cafe_place_tags.py` 방식 | 구현 단순, 추천 API에서 DB 조회 가능 | 지도 API 저장 정책과 데이터 출처 표기 주의 |
| 카페 태그만 별도 관리 | 외부 장소 ID 기준으로 태그 후보만 매칭 | 외부 API 실시간 검색과 잘 맞음 | 별도 모델 또는 매칭 로직 필요 |

현재 문서는 이미 구현된 명령어 기준으로 안내하되, 최종 방향은 팀에서 확정해야 합니다.

---

## 11. 에러 대응

### 11.1 LFS 포인터 에러

```text
Git LFS 실제 파일이 아니라 포인터 파일입니다.
```

해결:

```bash
git lfs pull
```

### 11.2 파일 없음 에러

```text
파일을 찾을 수 없습니다
```

확인할 것:

1. 현재 위치가 `backend`인지 확인합니다.
2. `backend/recommendations/fixtures/places` 또는 `backend/recommendations/fixtures/tags`에 파일이 있는지 확인합니다.
3. Git LFS 파일이 실제로 내려받아졌는지 확인합니다.

### 11.3 좌표 없는 데이터 스킵

`Place`는 장소명과 좌표가 있어야 저장됩니다. 위도 또는 경도가 없으면 스킵됩니다.

좌표가 누락된 데이터는 별도 review 파일로 분리하거나, geocoding 후 다시 import합니다.

---

## 12. 팀 공유용 요약

현재 DB 생성은 `loaddata`가 아니라 custom management command로 진행합니다.

현재 바로 실행 가능한 것은 다음입니다.

```text
Place import: beach, freewifi, shelter, toilet, smoking
Tag import: cafe 태그 import만 구현됨
흡연구역 세부 태그: Place import 중 조건부 생성
```

아직 남은 것은 다음입니다.

```text
citypark, parking, tourism Place import 설정 추가
beach, park, parking, shelter, toilet, tourism 공통 PlaceTag import 명령어 구현
카페 데이터를 Place에 저장할지, 외부 장소 태그 매칭 구조로 분리할지 최종 결정
```

따라서 지금 단계에서는 먼저 구현 완료된 Place 5종과 카페 태그 import를 dry-run으로 확인하고, 이후 나머지 Place와 공통 PlaceTag import 명령어를 추가하는 순서로 진행합니다.
