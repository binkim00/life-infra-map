# DB 생성 명령어 안내

이 문서는 프로젝트 실행을 위해 로컬 DB를 생성하고, 최종 장소/태그 데이터를 적재하는 방법을 정리합니다.

현재 프로젝트는 데이터 수집·정제·태그 생성 과정을 거쳐 최종 DB 상태를 `dumpdata`로 저장해 두었습니다. 따라서 일반 실행 환경에서는 복잡한 import 명령어를 다시 실행하지 않고, `loaddata`로 최종 DB를 복원하는 방식을 사용합니다.

DB는 PostgreSQL 16 + PostGIS로 고정되어 있으며 Django와 Spring이 같은 데이터베이스를 공유합니다. 선택 이유와 이관 검증은 `docs/02_data/postgres-migration.md`에 정리했습니다.

---

## 1. 브랜치 이동

```bash
git fetch origin
git checkout kyb
git pull origin kyb
```

`kyb` 브랜치의 최신 작업 내용을 받아옵니다.

---

## 2. Git LFS 파일 받기

```bash
git lfs install
git lfs pull
```

대용량 JSON 파일은 Git LFS로 관리되므로 실제 파일을 내려받습니다.

---

## 3. 백엔드 폴더로 이동

```bash
cd backend
```

Django 명령어는 `backend` 폴더에서 실행합니다.

---

## 4. 패키지 설치

```bash
pip install -r requirements.txt
```

Django 실행에 필요한 패키지를 설치합니다.

---

## 5. DB 준비

### 5.1 PostgreSQL 컨테이너 실행

DB는 Docker로 실행합니다. 로컬에 PostgreSQL을 설치하면 5432 포트가 충돌하므로 설치하지 않습니다.

프로젝트 루트에서 실행합니다.

```bash
docker compose up -d db
```

컨테이너를 처음 만들 때 `docker/postgres/init/01-extensions.sql`이 실행되어 `postgis`, `pg_trgm`, `unaccent` 확장이 켜집니다.

준비 상태를 확인합니다.

```bash
docker compose ps
```

`db`가 `healthy`로 표시되면 다음 단계로 넘어갑니다.

### 5.2 환경변수 설정

`backend/.env`에 다음 값을 넣습니다.

```text
POSTGRES_DB=life_infra_map
POSTGRES_USER=life_infra_map
POSTGRES_PASSWORD=life_infra_map
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

### 5.3 DB를 완전히 새로 만들 경우

컨테이너와 데이터 볼륨을 함께 지웁니다.

```bash
docker compose down -v
docker compose up -d db
```

`down -v`는 DB 데이터를 삭제합니다. 되돌릴 수 없으므로 실행 전에 확인합니다.

---

## 6. DB 마이그레이션

```bash
python manage.py migrate
```

현재 모델 구조를 DB에 반영합니다.

보통 프로젝트에 migration 파일이 이미 포함되어 있으므로 일반 실행 환경에서는 `makemigrations`를 실행하지 않습니다.
모델을 직접 수정한 경우에만 별도로 `makemigrations`를 실행합니다.

`0009_place_geography_index`가 `Place`에 PostGIS `geog` 생성 컬럼과 GiST 인덱스를 만듭니다.

적용 결과를 확인합니다.

```bash
python manage.py showmigrations recommendations
```

`0009`까지 `[X]`로 표시되어야 합니다.

---

## 7. 최종 DB 데이터 적재

최종 DB 데이터는 아래 3개 fixture로 관리합니다.

```text
backend/recommendations/fixtures/loaddata/tags.json
backend/recommendations/fixtures/loaddata/places.json
backend/recommendations/fixtures/loaddata/place_tags.json
```

적재 순서는 중요합니다.
`PlaceTag`가 `Place`와 `Tag`를 참조하므로 `Tag`, `Place`, `PlaceTag` 순서로 넣습니다.

```bash
python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/tags.json
python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/places.json
python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/place_tags.json
```

Windows 환경에서는 한글 및 특수문자 인코딩 문제를 피하기 위해 `python -X utf8` 옵션을 사용합니다.

---

## 8. 최종 DB 적재 결과 확인

```bash
python manage.py shell
```

```python
from recommendations.models import Place, Tag, PlaceTag
from django.db.models import Count

print("Place:", Place.objects.count())
print("Tag:", Tag.objects.count())
print("PlaceTag:", PlaceTag.objects.count())

for row in PlaceTag.objects.values("place__category").annotate(count=Count("id")).order_by("place__category"):
    print(row)
```

`loaddata` 직후 기대값은 다음과 같습니다.

```text
Place: 215398
Tag: 133
PlaceTag: 571177
```

카테고리별 `PlaceTag` 기준 기대값은 다음과 같습니다.

```text
beach: 1358
cafe: 7359
city_park: 63356
freewifi: 190
parking: 58003
shelter: 326806
smoking_area: 856
toilet: 112675
tourism: 574
```

`pgAdmin`으로 확인하려면 `docs/02_data/pgadmin-guide.md`를 참고하세요.

### fixture와 현재 개발 DB의 차이

위 fixture는 **2026년 7월 7일 기준 스냅샷**입니다. 이후 `repair_place_data` 커맨드를 적용해 현재 개발 DB와 값이 달라졌습니다.

| 항목 | fixture (`loaddata` 결과) | 현재 개발 DB |
|---|---|---|
| `Place` | 215,398 | 215,436 |
| `Tag` | 133 | 133 |
| `PlaceTag` | 571,177 | 571,177 |
| `beach` | 1,358 | 1,428 |
| `city_park` | 63,356 | 62,879 |
| `parking` | 58,003 | 58,552 |
| `tourism` | 574 | 432 |

`Place`는 38건이 추가되었고, `PlaceTag` 총 건수는 같지만 일부 장소의 카테고리가 재분류되어 분포가 달라졌습니다.

이 차이는 fixture를 다시 만들지 않고 커맨드로 재현합니다. 다음 항목으로 넘어가세요.

---

## 9. 장소 데이터 교정

`loaddata`만 하면 아래 두 가지 오류가 남아 있습니다. 이는 fixture 생성 시점 이후에 발견된 문제입니다.

| 문제 | 내용 |
|---|---|
| 카테고리 오분류 | 같은 카카오 장소가 여러 카테고리 시드에 있으면 `(source, external_id)` 유니크 제약 때문에 나중에 임포트된 카테고리가 남습니다. 광안리·송도·송정해수욕장이 `tourism`으로 저장된 원인입니다. |
| 해수욕장 누락 | `import_fixture_places`가 `external_places`를 건너뛰기 때문에, 카카오 매칭에 실패한 해수욕장(해운대 등)이 어느 쪽으로도 저장되지 않았습니다. |

교정 커맨드를 실행합니다.

```bash
python manage.py repair_place_data --dry-run   # 바뀔 내용만 출력
python manage.py repair_place_data             # 실제 교정
```

이 커맨드는 `ExData/Cleaned/beach_places.json`을 읽으므로 `git lfs pull`이 끝난 상태여야 합니다.

실행 후 기대값은 다음과 같습니다.

```text
Place: 215436
Tag: 133
PlaceTag: 571177
```

```text
beach: 1428
cafe: 7359
city_park: 62879
freewifi: 190
parking: 58552
shelter: 326806
smoking_area: 856
toilet: 112675
tourism: 432
```

커맨드는 멱등이므로 여러 번 실행해도 안전합니다. 이미 교정된 DB에서 실행하면 다음과 같이 출력됩니다.

```text
[1] 카테고리 교정
  교정 대상 없음

[2] 누락 해수욕장 적재
  적재할 항목 없음
```

---

## 10. 전체 실행 순서 요약

새 환경에서 DB를 다시 만드는 기본 순서는 다음과 같습니다.

```bash
git fetch origin
git checkout kyb
git pull origin kyb

git lfs install
git lfs pull

# 프로젝트 루트에서 DB 컨테이너 실행
docker compose up -d db

cd backend

pip install -r requirements.txt

python manage.py migrate

python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/tags.json
python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/places.json
python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/place_tags.json

python manage.py repair_place_data
```

마지막 `repair_place_data`까지 실행해야 현재 개발 DB와 같은 상태가 됩니다.

DB를 완전히 비우고 다시 만들려면 `docker compose down -v` 후 다시 올립니다.

---

# 참고: 원본 seed에서 DB를 다시 생성하는 경우

아래 내용은 일반 실행용이 아니라, 데이터 정제 결과를 다시 검증하거나 최종 `loaddata` fixture를 새로 만들 때 사용하는 절차입니다.

일반 팀원 실행 환경에서는 이 과정을 반복할 필요가 없습니다.

---

## 1. 장소 데이터 import

```bash
python manage.py import_fixture_places --only toilet freewifi smoking beach citypark parking tourism --dry-run
python manage.py import_fixture_places --only toilet freewifi smoking beach citypark parking tourism
```

현재 장소 import 대상은 다음입니다.

```text
toilet
freewifi
smoking
beach
citypark
parking
tourism
```

`shelter`는 일반 장소 fixture의 `place_candidates`가 없기 때문에 이 단계에서는 넣지 않습니다.
`shelter`는 태그 seed 기반으로 Place를 생성하는 방식으로 처리합니다.

---

## 2. external place tag seed 생성

`beach`, `park`, `parking`, `tourism` 중 external place로 분리된 장소는 카카오 장소 ID 기준으로 태그 seed를 변환합니다.

```bash
python build_external_place_tag_seed.py --only beach tourism parking park
```

생성되는 파일은 다음 위치에 저장됩니다.

```text
recommendations/fixtures/tags/external/
```

---

## 3. external place tag import

```bash
python manage.py import_external_place_tags --only beach tourism parking park --dry-run
python manage.py import_external_place_tags --only beach tourism parking park
```

이 명령어는 `kakao_local` source 기준의 `Place`와 `PlaceTag`를 생성합니다.

---

## 4. 내부 Place 기준 공통 태그 import

```bash
python manage.py import_fixture_place_tags --only toilet beach park parking tourism
```

이 명령어는 이미 DB에 존재하는 내부 `Place`에 태그를 연결합니다.

---

## 5. shelter 태그 및 장소 import

`shelter`는 기존 `Place`가 없기 때문에 태그 seed에서 Place를 같이 생성합니다.

먼저 일부만 테스트합니다.

```bash
python manage.py import_fixture_place_tags --only shelter --create-missing-places --limit 1000 --dry-run
```

문제가 없으면 전체를 실행합니다.

```bash
python manage.py import_fixture_place_tags --only shelter --create-missing-places
```

주의: `--create-missing-places` 옵션은 전체 데이터에 사용하지 않습니다.

아래 명령어는 실행하지 않습니다.

```bash
python manage.py import_fixture_place_tags --only all --create-missing-places
```

이 명령어를 전체에 사용하면 `beach`, `park`, `parking`, `tourism`의 unresolved row까지 내부 Place로 생성될 수 있어 중복 또는 품질 문제가 생길 수 있습니다.

---

## 6. cafe import

```bash
python manage.py import_cafe_place_tags --min-confidence 70 --dry-run
python manage.py import_cafe_place_tags --min-confidence 70
```

카페는 `kakao_local` 장소 기준으로 Place와 PlaceTag를 생성합니다.

---

## 7. 최종 DB 확인

```bash
python manage.py shell
```

```python
from recommendations.models import Place, Tag, PlaceTag
from django.db.models import Count

print("Place:", Place.objects.count())
print("Tag:", Tag.objects.count())
print("PlaceTag:", PlaceTag.objects.count())

for row in PlaceTag.objects.values("place__category").annotate(count=Count("id")).order_by("place__category"):
    print(row)
```

---

## 8. 최종 loaddata fixture 생성

DB가 완성되면 최종 복원용 fixture를 생성합니다.

```bash
mkdir -p recommendations/fixtures/loaddata

python -X utf8 manage.py dumpdata recommendations.Tag --indent 2 -o recommendations/fixtures/loaddata/tags.json
python -X utf8 manage.py dumpdata recommendations.Place --indent 2 -o recommendations/fixtures/loaddata/places.json
python -X utf8 manage.py dumpdata recommendations.PlaceTag --indent 2 -o recommendations/fixtures/loaddata/place_tags.json
```

Windows 환경에서는 `cp949` 인코딩 문제를 피하기 위해 `python -X utf8` 옵션을 사용합니다.

---

## 9. 데이터 파일 관리 기준

최종 실행에 필요한 파일은 아래 3개입니다.

```text
backend/recommendations/fixtures/loaddata/tags.json
backend/recommendations/fixtures/loaddata/places.json
backend/recommendations/fixtures/loaddata/place_tags.json
```

원본 및 정제 과정 데이터는 `ExData`에 보관합니다.

```text
ExData/CSVData/
ExData/JsonData/
ExData/Cleaned/
ExData/ImportPlan/final/
ExData/TagSeeds/
ExData/Reference/
```

`Test` 폴더에는 테스트 스크립트만 남기고, 중간 결과 JSON/CSV 파일은 보관하지 않습니다.
