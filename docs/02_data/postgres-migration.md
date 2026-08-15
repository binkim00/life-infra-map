# DB 전환 기록: SQLite → PostgreSQL

이 문서는 프로젝트 DB를 SQLite에서 PostgreSQL로 바꾼 이유와 결과를 정리합니다.

전환은 완료되었습니다. 관련 커밋은 `434ca25`(Postgres 전환 및 로컬 DB 컨테이너 구성), `6d3f273`(반경/거리 계산을 PostGIS로 이전)입니다. 현재 애플리케이션은 PostgreSQL/PostGIS 전용이며 예전 DB 엔진으로 돌아가는 실행 경로는 제거했습니다.

---

## 1. 무엇에서 무엇으로 바꿨는지

| 항목 | 기존 | 현재 |
|---|---|---|
| DBMS | SQLite 3 | PostgreSQL 16 |
| 공간 확장 | 없음 | PostGIS 3.4 |
| 실행 방식 | `backend/db.sqlite3` 파일 | Docker 컨테이너 (`postgis/postgis:16-3.4`) |
| Django ENGINE | `django.db.backends.sqlite3` | `django.db.backends.postgresql` |
| 드라이버 | Python 내장 `sqlite3` | `psycopg[binary]==3.2.10` |
| 활성 확장 | 없음 | `postgis`, `pg_trgm`, `unaccent` |
| 반경/거리 계산 | bounding box + 파이썬 하버사인 | `ST_DWithin` + `ST_Distance` (GiST 인덱스) |
| 연결 관리 | 해당 없음 | `CONN_MAX_AGE=60`, `connect_timeout=5` |

현재 Django 설정은 `django.db.backends.postgresql`로 고정되어 있습니다. 접속 대상만 `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`로 지정합니다.

---

## 2. 왜 바꿨는지

### 2.1 사용자가 데이터를 계속 쓰는 서비스가 되었다

초기에는 공공데이터를 읽어서 보여주는 것이 중심이었으므로 SQLite로 충분했습니다.

이후 장소 제보, 오류 제보, 게시글, 댓글, 좋아요, 신고, 장소 저장 기능이 들어오면서 쓰기 요청이 상시 발생하는 구조가 되었습니다.

SQLite는 쓰기 시 **데이터베이스 파일 전체를 잠급니다.** 동시에 쓰기가 들어오면 뒤의 요청은 대기하다 `database is locked`로 실패합니다. 여러 사용자가 동시에 제보하거나 글을 쓰는 상황을 감당할 수 없습니다.

PostgreSQL은 행 수준 잠금과 MVCC를 사용하므로 읽기가 쓰기를 막지 않고, 서로 다른 행에 대한 쓰기가 동시에 처리됩니다.

### 2.2 반경/거리 계산을 DB에서 할 수 없었다

이 서비스의 핵심 질의는 "내 위치에서 반경 N미터 안의 장소"입니다.

SQLite에는 공간 인덱스가 없으므로 다음 두 단계로 처리하고 있었습니다.

```text
1. SQL 에서 bounding box(사각형)로 대략 좁힌다
2. 파이썬에서 행마다 하버사인 공식을 돌려 반경 밖을 걸러낸다
```

사각형은 원보다 넓으므로 불필요한 행을 읽고, 걸러내는 계산이 애플리케이션에서 행 단위로 반복됩니다. Place가 215,436건이라 이 비용이 응답 시간의 대부분을 차지했습니다.

PostGIS의 `ST_DWithin`은 정확한 반경 조건을 GiST 인덱스로 처리하므로 두 단계가 한 번의 질의로 끝납니다.

### 2.3 질의 최적화 수단이 필요했다

SQLite에는 부분 인덱스 정도만 있고, 이 프로젝트가 필요한 다음 수단이 없습니다.

| 필요한 것 | 용도 |
|---|---|
| GiST 인덱스 | 좌표 반경 검색 |
| GIN + `pg_trgm` | 장소명/주소 부분 일치 검색 |
| `jsonb` | `Place.raw` 원본 데이터 조회 |
| 실행 계획 및 통계 | `EXPLAIN ANALYZE`로 느린 질의 원인 확인 |

전환 과정에서 `EXPLAIN`으로 확인해 고친 문제가 실제로 있었습니다. `apply_keyword_filter`의 `.distinct()`가 `raw`(JSONField)를 포함한 810바이트 전체 행을 정렬하면서 디스크로 스필하고 있었습니다(`Sort Method: external merge Disk: 3664kB`). SQLite에서는 이런 진단 자체가 어렵습니다.

### 2.4 지금이 이관 비용이 가장 싼 시점이었다

전환 시점의 데이터 구성은 다음과 같았습니다.

| 구분 | 건수 | 비율 |
|---|---|---|
| 참조 데이터 (`Place` 215,436 + `PlaceTag` 571,177 + `Tag` 133) | 786,746 | 99.98% |
| Django 기본 데이터 (`ContentType` 26 + `Permission` 104) | 130 | 0.017% |
| 사용자 생성 데이터 (`User` 1 + `Post` 5) | 6 | 0.0008% |
| 합계 | 786,882 | |

참조 데이터는 언제든 다시 만들 수 있고, 지켜야 할 사용자 데이터는 6건뿐이었습니다. 사용자가 늘어난 뒤에 옮기면 무중단 이관과 데이터 검증 부담이 생기므로, 사용자 데이터가 사실상 없는 지금이 가장 안전한 시점이었습니다.

### 2.5 배포 환경과 개발 환경을 맞춰야 했다

SQLite는 파일이므로 컨테이너로 배포하면 재시작마다 데이터가 사라지고, 인스턴스를 여러 개 띄우면 파일을 공유할 수 없습니다. 개발은 SQLite, 배포는 PostgreSQL로 나누면 개발 중에 발견되지 않는 문제가 생깁니다.

---

## 3. 왜 PostgreSQL을 골랐는지

| 후보 | 판단 |
|---|---|
| PostgreSQL | 선택. PostGIS로 반경 질의를 인덱스로 처리할 수 있고, `jsonb`로 `Place.raw`를 다룰 수 있으며, `pg_trgm`으로 한글 부분 일치 검색을 확장할 여지가 있습니다. Django가 가장 잘 지원하는 DB이기도 합니다. |
| MySQL | 공간 기능이 있으나 PostGIS만큼 함수와 인덱스 지원이 넓지 않습니다. JSON 처리와 부분 일치 검색 확장도 약합니다. |
| SQLite 유지 | 2.1~2.5의 문제가 해결되지 않습니다. |

---

## 4. 어떻게 이관했는지

`dumpdata`/`loaddata`는 786,882건을 한 번에 JSON으로 만들면서 메모리를 크게 쓰기 때문에 사용하지 않았습니다.

대신 당시 전용 관리 명령어를 만들어 일회성으로 이관했습니다. 이관 완료 후 해당 명령과 레거시 DB 연결은 제거했습니다.

동작 방식은 다음과 같습니다.

- 두 데이터베이스를 동시에 연결해 원본을 읽기 전용으로 조회
- 외래키가 가리키는 쪽부터 순서대로 모델별 복사
- `iterator()`로 SQLite를 스트리밍해 메모리 사용을 억제
- 2,000건 단위 `bulk_create`
- PK를 그대로 유지하므로, 끝난 뒤 `setval`로 시퀀스를 `MAX(id)`에 맞춤

PK를 유지한 이유는 `PlaceTag` 571,177건이 `Place.id`를 참조하기 때문입니다. PK가 바뀌면 참조를 전부 다시 매핑해야 합니다.

시퀀스 재설정을 하지 않으면 시퀀스가 1에 머물러 있어서 새 글을 쓸 때 중복 키 오류가 납니다.

---

## 5. 결과

### 5.1 응답 시간

`6d3f273` 커밋에서 측정한 값입니다. 부산 서면 기준입니다.

`search_saved_places` (DB 질의만)

| 질의 | 이전 | 이후 |
|---|---|---|
| 화장실 | 260ms | 8ms |
| 공영주차장 | 272ms | 20ms |
| 주차장 말고 화장실 | 237ms | 8ms |
| 장애인 | 281ms | 9ms |

`/map-search` API (카카오 호출 포함)

| 질의 | 이전 | 이후 |
|---|---|---|
| 화장실 | 298ms | 167ms |
| 장애인 | 282ms | 157ms |

`.distinct()` 수정 건은 별도로 공영주차장 4필드 OR 질의가 1,159ms에서 272ms로 줄었습니다.

### 5.2 거리 값 정확도

PostGIS는 타원체 기준이라 기존 구면 하버사인과 값이 조금 다릅니다. 검증 결과 최대 4.6m, 평균 1.5m 차이이며 PostGIS 쪽이 더 정확합니다.

### 5.3 스키마 변경

`Place`에 `geog` 컬럼이 추가되었습니다(마이그레이션 `0009_place_geography_index`).

```sql
geog geography(Point, 4326)
GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography) STORED
```

생성 컬럼이므로 애플리케이션이 값을 채울 필요가 없습니다. 기존 `lat`/`lng` 컬럼은 외부 API와 좌표를 교환하기 위해 함께 유지합니다. GiST 인덱스 크기는 약 16MB입니다.

---

## 6. 검증 결과

이관 당시 원본과 PostgreSQL의 건수를 비교한 결과입니다.

| 모델 | SQLite | PostgreSQL | 비고 |
|---|---|---|---|
| `contenttypes.ContentType` | 26 | 26 | |
| `auth.Permission` | 104 | 104 | |
| `auth.User` | 1 | 2 | 이관 후 PostgreSQL에서 테스트 계정 1건 생성 |
| `recommendations.Tag` | 133 | 133 | |
| `recommendations.Place` | 215,436 | 215,436 | |
| `recommendations.PlaceTag` | 571,177 | 571,177 | |
| `boards.Post` | 5 | 5 | |
| 합계 | 786,882 | 786,883 | |

그 외 모델은 양쪽 모두 0건입니다.

추가로 확인한 항목입니다.

- 마이그레이션 `0001`~`0009` 전부 적용됨
- `recommendations_place_id_seq`의 현재 값이 `MAX(id)`인 215,436과 일치 (시퀀스 재설정 정상)
- `geog` 생성 컬럼과 `recommendations_place_geog_gist` 인덱스 존재
- 테스트 348개 PostgreSQL에서 통과 (`434ca25`, `6d3f273` 기준)

---

## 7. 현재 운영 기준

PostgreSQL/PostGIS가 유일한 데이터베이스입니다. Django와 Spring은 같은 데이터베이스를 공유하며 Django가 마이그레이션을 소유합니다. 로컬 환경도 Docker Compose의 `db` 서비스를 사용하므로 별도 파일 DB나 엔진 전환 스위치는 제공하지 않습니다.

---

## 8. 남은 작업

| 항목 | 내용 |
|---|---|
| trigram 인덱스 | 측정 결과 플래너가 순차 스캔을 선택했고(Parallel Seq Scan 36ms vs 강제 Bitmap Index Scan 132ms), 한글 3글자 토큰의 선택도가 낮아 보류했습니다. `pg_trgm` 확장은 켜 두었으므로 테이블이 100만 건을 넘으면 재검토합니다. |
| `django.contrib.gis` | 현재 PostGIS 질의는 raw SQL로 처리합니다. `GeoDjango` 백엔드(`django.contrib.gis.db.backends.postgis`)와 `PointField`로 옮기는 것은 이후 판단합니다. |
| loaddata fixture | `recommendations/fixtures/loaddata/`의 fixture는 2026년 7월 7일 기준 스냅샷입니다. 차이는 `repair_place_data` 커맨드로 재현되므로 fixture를 다시 만들지 않습니다. 절차는 `docs/02_data/db-seed-import-guide.md`의 9번 항목에 있습니다. |

---

## 9. 관련 문서

- `docs/02_data/pgadmin-guide.md` — DB 데이터를 브라우저에서 확인하는 방법
- `docs/02_data/db-seed-import-guide.md` — 새 환경에서 DB를 만들고 데이터를 적재하는 절차
