# DB 생성 명령어 안내

이 문서는 프로젝트 실행을 위해 로컬 DB를 생성하고, 최종 장소/태그 데이터를 적재하는 방법을 정리합니다.

현재 프로젝트는 데이터 수집·정제·태그 생성 과정을 거쳐 최종 DB 상태를 `dumpdata`로 저장해 두었습니다. 따라서 일반 실행 환경에서는 복잡한 import 명령어를 다시 실행하지 않고, `loaddata`로 최종 DB를 복원하는 방식을 사용합니다.

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

## 5. DB 초기화

기존 DB를 새로 만들 경우 `db.sqlite3`를 삭제합니다.

```bash
rm db.sqlite3
```

Windows에서 DB가 사용 중이면 삭제가 실패할 수 있습니다.

```text
rm: cannot remove 'db.sqlite3': Device or resource busy
```

이 경우 아래 항목을 닫고 다시 삭제합니다.

```text
- 실행 중인 Django 서버
- python manage.py shell
- VS Code SQLite/DB viewer
- DB Browser for SQLite
```

---

## 6. DB 마이그레이션

```bash
python manage.py migrate
```

현재 모델 구조를 DB에 반영합니다.

보통 프로젝트에 migration 파일이 이미 포함되어 있으므로 일반 실행 환경에서는 `makemigrations`를 실행하지 않습니다.
모델을 직접 수정한 경우에만 별도로 `makemigrations`를 실행합니다.

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

현재 최종 DB 기준 기대값은 다음과 같습니다.

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

---

## 9. 전체 실행 순서 요약

새 환경에서 DB를 다시 만드는 기본 순서는 다음과 같습니다.

```bash
git fetch origin
git checkout kyb
git pull origin kyb

git lfs install
git lfs pull

cd backend

pip install -r requirements.txt

rm db.sqlite3
python manage.py migrate

python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/tags.json
python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/places.json
python -X utf8 manage.py loaddata recommendations/fixtures/loaddata/place_tags.json
```

DB 삭제가 실패하면 실행 중인 서버, shell, DB viewer를 종료한 뒤 다시 삭제합니다.

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
