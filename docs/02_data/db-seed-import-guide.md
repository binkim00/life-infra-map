# DB 생성 명령어 안내

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

대용량 JSON 파일이 Git LFS로 관리되므로 실제 파일을 내려받습니다.

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

## 5. DB 마이그레이션

```bash
python manage.py makemigrations
python manage.py migrate
```

현재 모델 구조를 DB에 반영합니다.

---

## 6. 장소 데이터 import 테스트

```bash
python manage.py import_fixture_places --only all --dry-run
```

실제 DB에 저장하지 않고 장소 데이터 import가 가능한지 먼저 확인합니다.

현재 `import_fixture_places --only all`에 포함되는 대상은 다음입니다.

```text
beach
freewifi
shelter
toilet
smoking
```

---

## 7. 장소 데이터 import 실행

```bash
python manage.py import_fixture_places --only beach freewifi shelter toilet smoking
```

정제된 장소 데이터를 `Place` 테이블에 저장합니다.

현재 `citypark`, `parking`, `tourism` 장소 파일은 있지만 `import_fixture_places.py` 설정에는 아직 포함되어 있지 않으므로 위 명령어로는 들어가지 않습니다.

---

## 8. 카페 태그 import 테스트

```bash
python manage.py import_cafe_place_tags --min-confidence 70 --dry-run
```

신뢰도 70 이상인 카페 태그 후보를 실제 저장 없이 확인합니다.

---

## 9. 카페 태그 import 실행

```bash
python manage.py import_cafe_place_tags --min-confidence 70
```

카페 장소와 태그 후보를 `Place`, `Tag`, `PlaceTag`에 저장합니다.

---

## 10. 공통 태그 import 테스트

```bash
python manage.py import_fixture_place_tags --only all --dry-run
```

카페를 제외한 공통 태그 seed를 실제 저장 없이 확인합니다.

현재 공통 태그 import 대상은 다음입니다.

```text
beach
park
parking
shelter
toilet
tourism
```

단, 기본 동작은 이미 DB에 존재하는 `Place`에만 태그를 붙입니다.
매칭되는 `Place`가 없으면 해당 태그 row는 스킵됩니다.

---

## 11. 공통 태그 import 실행

```bash
python manage.py import_fixture_place_tags --only all
```

기존 `Place`와 매칭되는 태그를 `Tag`, `PlaceTag`에 저장합니다.

일부만 테스트하려면 다음처럼 실행합니다.

```bash
python manage.py import_fixture_place_tags --only toilet --limit 100 --dry-run
python manage.py import_fixture_place_tags --only beach park toilet --dry-run
```

---

## 12. 태그 seed 기준으로 장소까지 같이 생성하는 경우

공통 태그 import 중 기존 `Place`를 찾지 못한 row도 장소로 만들고 싶으면 `--create-missing-places` 옵션을 사용합니다.

```bash
python manage.py import_fixture_place_tags --only all --create-missing-places --dry-run
```

결과를 확인한 뒤 실제 저장합니다.

```bash
python manage.py import_fixture_place_tags --only all --create-missing-places
```

이 방식은 태그 seed row에 들어 있는 최소 장소 정보로 `Place`를 생성합니다.
따라서 원본 장소 fixture를 import하는 방식보다 `raw`, `source_updated_at`, `data_quality_score` 같은 정보가 부족할 수 있습니다.

가능하면 `Place` import를 먼저 완성한 뒤 공통 태그 import를 실행하는 것이 더 깔끔합니다.

---

## 13. DB 저장 결과 확인

```bash
python manage.py shell
```

```python
from recommendations.models import Place, Tag, PlaceTag
from django.db.models import Count

Place.objects.count()
Tag.objects.count()
PlaceTag.objects.count()

Place.objects.values("category").annotate(count=Count("id")).order_by("category")
PlaceTag.objects.values("source", "status").annotate(count=Count("id")).order_by("source", "status")
```

장소, 태그, 장소-태그 연결 데이터가 정상적으로 들어갔는지 확인합니다.

---

## 14. 실행 순서 요약

기본 실행 순서는 다음과 같습니다.

```bash
git lfs install
git lfs pull

cd backend

python manage.py makemigrations
python manage.py migrate

python manage.py import_fixture_places --only all --dry-run
python manage.py import_fixture_places --only beach freewifi shelter toilet smoking citypark parking tourism

python manage.py import_cafe_place_tags --min-confidence 70 --dry-run
python manage.py import_cafe_place_tags --min-confidence 70

python manage.py import_fixture_place_tags --only all --dry-run
python manage.py import_fixture_place_tags --only all
```

기존 Place가 없는 태그 row까지 장소로 같이 만들 경우에는 마지막 공통 태그 import를 아래처럼 실행합니다.

```bash
python manage.py import_fixture_place_tags --only all --create-missing-places --dry-run
python manage.py import_fixture_place_tags --only all --create-missing-places
```
