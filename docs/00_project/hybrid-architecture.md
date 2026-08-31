# 하이브리드 구조 (Django + Spring, 단일 PostgreSQL)

이 문서는 Django와 Spring 두 API 서버가 하나의 PostgreSQL을 공유하는 현재 구조와, 그렇게 정한 이유를 정리합니다.

API 분리는 끝났습니다. 검색은 Django, 나머지는 Spring 이 담당합니다. 남은 것은 회원가입(파일 업로드) 하나입니다.

---

## 1. 무엇을 하이브리드라고 부르는지

API 서버는 두 개(Django, Spring), 데이터베이스는 한 개(PostgreSQL)인 구조입니다.

```text
서버는 나눈다  →  기능별로 Django / Spring
DB 는 나누지 않는다  →  life_infra_map 하나를 공유
```

"서비스를 나눈다"와 "DB를 나눈다"는 별개의 결정입니다. 이 프로젝트는 **앞의 것만** 했습니다. 이유는 3번과 6번에 있습니다.

---

## 2. 전체 구성도

```text
                    ┌──────────────────────┐
                    │  React (:5173)       │
                    └──────────┬───────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
   ┌────────────────────┐          ┌────────────────────┐
   │  Django (:8000)    │          │  Spring (:8081)    │
   │  DRF               │          │  Spring Boot 3.4   │
   │  psycopg 3         │          │  JDBC + HikariCP   │
   │  스키마 소유자      │          │  ddl-auto: validate│
   └─────────┬──────────┘          └─────────┬──────────┘
             │                               │
             │      127.0.0.1:5432           │
             └───────────────┬───────────────┘
                             ▼
                ┌──────────────────────────┐
                │  호스트 포트 5432         │  docker-compose 포트 매핑
                └────────────┬─────────────┘
                             ▼
   ┌──────────────────────────────────────────────────┐
   │  life-infra-map-db (postgis/postgis:16-3.4)      │
   │  DB: life_infra_map                              │
   │  확장: postgis, pg_trgm, unaccent                │
   └──────────────────────▲───────────────────────────┘
                          │  db:5432 (컨테이너 네트워크)
                 ┌────────┴─────────┐
                 │  pgAdmin (:5050) │
                 └──────────────────┘

   ┌──────────────────────────────────────────────────┐
   │  life-infra-map-storage (MinIO, :9000 / :9001)   │  업로드 파일
   └──────────────────────────────────────────────────┘
```

앱(Django, Spring, React)은 호스트에서 직접 실행하고, 인프라(DB, pgAdmin, MinIO)만 컨테이너로 띄웁니다.

---

## 3. 왜 서버를 분리하는지

### 3.1 두 영역의 성격과 변경 주기가 다르다

이 서비스의 백엔드는 성격이 뚜렷하게 다른 두 덩어리로 나뉩니다.

| | 인증 · 계정 · 게시판 | AI 추천 검색 |
|---|---|---|
| 요구사항 | 명확하고 고정적 | 계속 바뀜 |
| 스키마 | 거의 변하지 않음 | 후보 수집·판정 전략이 자주 변함 |
| 중요한 것 | **틀리지 않는 것** | **빠르게 실험하는 것** |
| 실패의 결과 | 로그인 불가, 데이터 손상 | 검색 품질 저하 |
| 변경 빈도 | 한 번 만들면 거의 안 건드림 | 프롬프트·모델·라우팅을 수시로 수정 |

전자는 컴파일 타임 검증과 명시적 트랜잭션 경계에서 이득이 크고, 후자는 인터프리터의 짧은 수정-확인 주기와 Python AI 생태계가 필요합니다. 요구하는 것이 반대입니다.

변경 빈도 차이도 실질적인 문제입니다. 한 서버에 있으면 AI 검색 프롬프트를 고칠 때마다 로그인 기능까지 함께 재시작됩니다. 분리하면 각자의 주기로 배포할 수 있습니다.

### 3.2 팀원 역량에 맞춰 병렬로 작업한다

Java/Spring을 담당하는 팀원과 Python/Django를 담당하는 팀원이 동시에 진행할 수 있습니다.

서버가 나뉘어 있으면 같은 파일을 고칠 일이 없으므로 코드 충돌 없이 각자 작업합니다. 두 서비스가 지켜야 할 계약은 두 가지로 좁혀집니다.

```text
1. HTTP API 규격 (경로, 요청/응답 형식)
2. DB 스키마와 JWT 클레임
```

단, **스키마 소유권은 한 곳(Django)으로 고정**했습니다. 이 부분을 나누면 병렬 작업의 이점이 사라지고 마이그레이션 충돌이 시작됩니다. 자세한 내용은 8번에 있습니다.

### 3.3 부하 특성이 다른 영역을 따로 확장할 수 있다

두 영역의 자원 사용 패턴이 다릅니다.

| | AI 추천 검색 | 인증 · 계정 |
|---|---|---|
| 요청당 시간 | 길다 (외부 API 대기) | 짧다 |
| 병목 | 네트워크 I/O (OpenAI, 카카오, 네이버) | CPU, DB |
| 호출 빈도 | 낮음 | 높음 |

한 서버에 있으면 AI 검색이 외부 응답을 기다리는 동안 워커를 점유해 로그인 요청까지 밀립니다. 분리해 두면 나중에 필요한 쪽만 인스턴스를 늘릴 수 있고, 실무에서 흔한 다중 서비스 구조를 경험한다는 목적도 함께 달성합니다.

### 3.4 분리의 비용도 인지하고 있다

분리는 공짜가 아닙니다.

| 늘어나는 것 | 내용 |
|---|---|
| 관리 지점 | 실행·배포·로그·환경변수가 두 벌 |
| 인증 동기화 | JWT 비밀키와 클레임을 양쪽이 맞춰야 함 |
| 프론트 라우팅 | 어느 경로가 어느 서버로 가는지 관리 필요 |
| 디버깅 | 문제가 어느 서비스에 있는지 먼저 판단해야 함 |

그래서 **분리 비용을 최소화하는 선택을 함께 했습니다.** DB를 나누지 않고(6번), 스키마 소유자를 하나로 고정하고(8번), 인증을 공유 비밀키로 통일한 것(9번)이 모두 여기에 해당합니다. 서버만 나누고 데이터 계층은 하나로 유지하는 것이 이 규모에서 얻을 것은 얻고 잃을 것은 피하는 지점입니다.

---

## 4. 각 프레임워크의 장점

### 4.1 Django

| 장점 | 이 프로젝트에서 실제로 쓰이는 곳 |
|---|---|
| **마이그레이션** | 스키마 변경 이력이 파일로 남고 순서가 보장됩니다. `0001`~`0009`가 그 기록이며, PostGIS 생성 컬럼 추가(`0009`)도 여기서 처리했습니다. 그래서 스키마 소유자를 Django로 정했습니다. |
| **Admin 자동 생성** | 제보 승인, 태그 검수, 신고 처리 화면을 모델만 등록하면 얻습니다. 관리자 화면을 직접 만들 필요가 없습니다. |
| **management command** | 장소 적재, 태그 생성, 데이터 복구, 검색 평가 도구를 ORM과 같은 코드로 작성합니다. |
| **fixtures** | `dumpdata`/`loaddata`로 DB 상태를 파일로 주고받습니다. |
| **Python 생태계** | OpenAI SDK, 데이터 정제 스크립트, 좌표·문자열 처리를 같은 언어로 씁니다. AI 검색 오케스트레이터가 Django에 있는 핵심 이유입니다. |
| **DRF** | serializer와 뷰로 API를 빠르게 만듭니다. |
| **짧은 수정-확인 주기** | 컴파일이 없어 프롬프트나 라우팅 규칙을 바꾸고 바로 확인합니다. AI 검색 튜닝에서 이 차이가 큽니다. |
| **ORM 질의 표현력** | `Q` 객체 조합, `annotate`, raw SQL 혼용이 자유롭습니다. PostGIS `ST_DWithin` 질의도 ORM 안에서 처리했습니다. |

### 4.2 Spring

| 장점 | 이 프로젝트에서 실제로 쓰이는 곳 |
|---|---|
| **컴파일 타임 타입 검증** | 엔티티 필드나 메서드 시그니처를 바꾸면 영향받는 곳을 컴파일러가 전부 찾아 줍니다. 인증·계정처럼 조용히 틀리면 안 되는 영역에서 값이 큽니다. |
| **`ddl-auto: validate`** | 엔티티 매핑과 실제 스키마가 다르면 **부팅 단계에서 실패**합니다. 스키마 불일치가 런타임까지 숨어 들어가지 않으며, 이 프로젝트에서 Django 스키마를 보호하는 실제 안전장치입니다. |
| **선언적 트랜잭션** | `@Transactional`로 경계가 코드에 드러납니다. 회원가입처럼 여러 테이블을 함께 쓰는 작업의 원자성을 읽어서 확인할 수 있습니다. |
| **Spring Security** | 인증·인가를 필터 체인으로 구성합니다. JWT 검증(`JwtAuthenticationFilter`), 비밀번호 인코더(`DjangoPasswordEncoder`), 경로별 권한을 표준 구조에 맞춰 넣습니다. |
| **HikariCP** | 성숙한 커넥션 풀이 기본 내장입니다. 풀 크기·타임아웃·누수 감지를 설정으로 다룹니다. |
| **JVM 처리량** | 외부 API를 기다리지 않는 정형 CRUD에서 요청 처리량이 높습니다. |
| **IDE·정적 분석 지원** | 타입 정보 기반의 자동완성과 리팩터링이 정확합니다. 코드베이스가 커질 때 유지보수 비용이 낮습니다. |

### 4.3 그래서 이렇게 배분했다

| 영역 | 담당 | 결정 근거 |
|---|---|---|
| 인증, 계정 | Spring | 규칙이 고정적이고 정확성이 최우선. Spring Security와 타입 검증의 이득이 큼 |
| 게시판 (예정) | Spring | 정형 CRUD. 트랜잭션 경계가 명확하고 변경이 적음 |
| AI 추천 검색 | Django | Python AI 생태계 필요. 실험 주기가 짧아야 함 |
| 장소·태그 데이터 | Django | management command 기반 적재·정제 도구가 이미 여기 있음 |
| 관리자 화면 | Django | Admin을 그대로 활용 |
| DB 스키마 | Django | 마이그레이션이 이력과 순서를 보장 |

원칙은 하나입니다. **정확성이 중요한 곳은 Spring, 변화가 빠른 곳은 Django.**

---

## 5. 역할 분담

기준은 **검색만 Django, 나머지는 Spring** 입니다.

| 영역 | 담당 | 상태 |
|---|---|---|
| 인증 (로그인, 토큰 발급) | Spring | 구현됨 (`POST /api/auth/login`) |
| 계정 (회원가입, 비밀번호 변경, 내 정보, 닉네임, 프로필, 마이페이지, 로그아웃) | Spring | 구현됨. 회원가입은 파일 업로드가 붙어 이관 완료 |
| 게시판 (글·댓글·좋아요·신고) | Spring | 구현됨 (`/api/boards/**`). 목록·상세는 비로그인도 조회 가능 |
| 알림 · 문의 | Spring | 구현됨 (`/api/notifications`, `/api/inquiries`) |
| 관리자 (사용자·제재·문의·신고) | Spring | 구현됨 (`/api/admin/**`) |
| 사용자 등급 · 기여도 | Spring | 구현됨 (`/api/tiers`, 인증 필요) |
| 저장 장소 | Spring | 구현됨 (`/api/recommendations/saved-places`) |
| 파일 업로드 (프로필·게시글·제보 사진) | Spring | 구현됨. Django 와 같은 버킷·키 규칙 |
| **장소 제보** | **Django 유지** | 승인이 `Place`/`PlaceTag` 를 직접 만들기 때문입니다. 아래 참고 |
| AI 자연어 추천 검색 | **Django 유지** | — |
| 일반 지도 검색 | **Django 유지** | — |
| 장소/태그 데이터 (`place`, `tag`, `placetag`) | **Django 유지** | — |
| 검색 개인화 (`usersearchlog`, `userpreference`) | **Django 유지** | 검색 로그에서 파생되고 검색에만 쓰임 |
| DB 스키마 (마이그레이션) | **Django 소유** | Spring 은 `ddl-auto: validate` |

검색을 Django에 남기는 이유는 AI 검색 오케스트레이터, PostGIS 반경 질의, 데이터 적재 커맨드가 모두 Django에 있고 옮길 이유가 없기 때문입니다.

### 장소 제보를 Django에 남긴 이유

한 번 Spring으로 옮겼다가 되돌렸습니다. 제보 승인이 상태 변경만 하는 것이 아니라 **검색 데이터를 직접 만들기** 때문입니다.

```text
review_place_report()
  └─ apply_place_report_approval(report)
       ├─ create_place_from_report()      → Place 생성
       └─ attach_report_tags_to_place()   → PlaceTag 부착
```

장소와 태그는 Django 소유이므로, 이 쓰기를 Spring이 하면 경계가 무너집니다. 그대로 두었으면 **태그 제보를 승인해도 검색에 잡히지 않는** 회귀가 났을 것입니다.

`PlaceReport` 엔티티는 Spring에 남겼습니다. 기여도 계산이 승인 건수를 **읽기만** 하기 때문입니다.

이 문제를 찾아낸 것은 URL을 내렸을 때 깨진 Django 테스트(`test_tag_suggestion_approval_makes_tag_searchable_on_general_map` 등)입니다. 얇은 래퍼만 보고 판단하면 놓치는 종류였습니다.

### 등급·기여도

등급·기여도는 게시판 활동과 승인된 장소 제보를 함께 봐야 계산됩니다. 게시판은 Spring 소유이고 제보는 Django 소유이지만, 기여도는 `PlaceReport` 를 읽기만 하므로 Spring 에서 계산합니다.

프론트엔드는 `src/api/serviceRoutes.js`에서 경로별로 담당 서비스를 판단해 보냅니다. 인증 헤더는 `Bearer` 하나로 통일했고, 두 서비스가 같은 JWT를 검증합니다.

### 회원가입만 Django에 남긴 이유

프로필 사진을 multipart 로 올리는데 Spring 쪽에 파일 업로드가 아직 없습니다. 자격증명이 두 종류가 되지 않도록 **Django 회원가입/로그인도 같은 JWT 를 발급**합니다 (`backend/accounts/tokens.py`). 기존 DRF 토큰 필드는 호환을 위해 함께 내려줍니다.

---

## 6. DB를 하나로 두는 이유

### 6.1 선택한 패턴

| 패턴 | 뜻 | 채택 |
|---|---|---|
| **Shared Database** | 여러 서비스가 하나의 DB를 공유 | **채택** |
| Database per Service | 서비스마다 자기 DB를 가짐 | 채택하지 않음 |

### 6.2 Database per Service 를 택하지 않은 이유

`auth_user`를 참조하는 외래키가 **23개**입니다.

```text
accounts_userprofile, authtoken_token, django_admin_log,
boards_post, boards_comment, boards_postlike, boards_commentlike,
boards_commentdislike, boards_report, boards_notification,
boards_inquiry, boards_userpenalty,
recommendations_placereport, recommendations_userpreference,
recommendations_usersavedplace, recommendations_usersearchlog, ...
```

Spring이 `auth_user`를 자기 DB로 가져가면 다음 문제가 생깁니다.

| 잃는 것 | 결과 |
|---|---|
| 외래키 제약 | "존재하지 않는 사용자가 쓴 게시글"을 DB가 막지 못합니다 |
| `JOIN` | "게시글 작성자 이름"을 가져오려면 API 호출이 필요하고, 목록 20건이면 호출도 20번입니다 |
| 트랜잭션 | 회원 탈퇴 시 사용자는 삭제되고 게시글은 남는 중간 상태가 실제로 발생합니다 |

정합성 책임이 DB에서 애플리케이션 코드로 넘어옵니다. 이벤트 동기화나 보상 트랜잭션을 직접 만들어야 하며, 현재 규모에서 얻는 것이 없습니다.

실무에서도 서비스를 분리할 때 DB는 마지막에 분리하거나 분리하지 않습니다.

### 6.3 샤딩과 혼동하지 않기

"DB를 나눈다"는 표현이 샤딩처럼 들리지만 축이 다릅니다.

| 용어 | 무엇을 나누나 | 목적 | 서버 수 |
|---|---|---|---|
| 수직 분할 (Database per Service) | 테이블/컬럼 | 서비스 경계 | 여러 대 |
| 파티셔닝 | 행 | 큰 테이블 관리 | 1대 |
| 샤딩 | 행 | 한 서버로 감당 안 되는 규모 | 여러 대 |
| 레플리카 | 나누지 않음 (복제) | 읽기 부하 분산 | 여러 대 |

파티셔닝과 샤딩은 사실상 같은 개념이고, 한 서버 안이냐 여러 서버냐가 차이입니다.

현재 DB 전체가 **524MB**(`Place` 269MB, `PlaceTag` 238MB)로 메모리에 통째로 들어가는 크기입니다. 샤딩은 한 테이블이 수천만 행, TB 단위가 될 때 꺼내는 수단이므로 이 프로젝트의 논의 대상이 아닙니다.

성능이 문제가 되면 꺼낼 순서는 다음과 같습니다.

```text
1. 인덱스        ← 완료 (PostGIS GiST, 260ms -> 8ms)
2. 질의 개선      ← 완료 (.distinct() 제거, 1,159ms -> 272ms)
3. 캐시
4. 읽기 레플리카
5. 파티셔닝
6. 샤딩
```

---

## 7. DB 연결 방식

두 서비스가 같은 DB에 붙지만 경로가 다릅니다.

### 7.1 Django

드라이버는 `psycopg[binary]==3.2.10`이고 설정은 `backend/config/settings.py`에 있습니다.

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "life_infra_map"),
        "USER": os.getenv("POSTGRES_USER", "life_infra_map"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "life_infra_map"),
        "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
}
```

접속 값은 `backend/.env`에서 `load_dotenv`로 읽으며 PostgreSQL 설정에 직접 적용됩니다.

### 7.2 Spring

드라이버는 `build.gradle`의 `runtimeOnly 'org.postgresql:postgresql'`(JDBC)이고 설정은 `application.yml`에 있습니다.

```yaml
spring:
  datasource:
    url: jdbc:postgresql://${POSTGRES_HOST:127.0.0.1}:${POSTGRES_PORT:5432}/${POSTGRES_DB:life_infra_map}
    username: ${POSTGRES_USER:life_infra_map}
    password: ${POSTGRES_PASSWORD:life_infra_map}
  jpa:
    hibernate:
      ddl-auto: validate
```

`jdbc:postgresql://호스트:포트/DB이름` 형식의 JDBC URL 한 줄로 표현하는 점이 다릅니다. Spring Boot가 이 값으로 HikariCP 커넥션 풀을 만들고, JPA/Hibernate가 풀에서 연결을 빌려 씁니다.

### 7.3 대조

| | Django | Spring |
|---|---|---|
| 드라이버 | psycopg 3 (Python) | PostgreSQL JDBC (Java) |
| 설정 위치 | `settings.py` + `.env` | `application.yml` |
| 표기 방식 | 키·값 딕셔너리 | JDBC URL |
| 연결 풀 | Django 자체 (`CONN_MAX_AGE=60`) | HikariCP (기본 10) |
| 스키마 권한 | 소유자 | 검증만 (`validate`) |
| 접속 계정 | `life_infra_map` | `life_infra_map` (동일) |

### 7.4 호스트명이 두 종류인 이유

`docker-compose.yml`의 포트 매핑이 다리 역할을 합니다.

```yaml
ports:
  - "${POSTGRES_PORT:-5432}:5432"   # 호스트 5432 -> 컨테이너 5432
```

| 접속 주체 | 실행 위치 | 호스트명 |
|---|---|---|
| Django, Spring | 호스트 | `127.0.0.1` |
| pgAdmin | 컨테이너 | `db` (compose 서비스명) |

pgAdmin만 `db`인 이유는 컨테이너 네트워크 안에서 바로 가기 때문입니다. 접속 실패가 자주 나는 지점입니다.

### 7.5 Spring 은 `.env` 를 읽지 않는다

`application.yml`의 `${POSTGRES_HOST:127.0.0.1}`은 **OS 환경변수 또는 기본값**을 쓰는 문법이며, Django의 `backend/.env` 파일을 읽지 않습니다.

즉 **설정값이 두 곳에서 따로 관리됩니다.**

```text
Django  backend/.env 를 load_dotenv 로 읽음
Spring  OS 환경변수를 읽고, 없으면 application.yml 의 기본값을 씀
```

두 서비스가 같은 DB와 같은 토큰을 쓰므로, 아래 값들은 **양쪽이 반드시 같아야 합니다.** 현재는 `application.yml` 기본값을 `backend/.env` 값과 같게 맞춰 두었기 때문에 환경변수를 설정하지 않아도 로컬에서 동작합니다.

| 용도 | Django (`backend/.env`) | Spring (`application.yml`) | 로컬 기본값 |
|---|---|---|---|
| DB 접속 | `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | 같은 이름 | `127.0.0.1:5432` / `life_infra_map` |
| **토큰 서명** | `JWT_SECRET` | 같은 이름 | `local-dev-secret-key-at-least-32-bytes-long` |
| 토큰 알고리즘 | `JWT_ALGORITHM` | `JwtService`에 HS256 고정 | `HS256` |
| 저장소 접속 | `S3_ACCESS_KEY` / `S3_SECRET_KEY` | 같은 이름 | `life_infra_map` / `life_infra_map_secret` |
| 버킷·엔드포인트 | `S3_BUCKET` / `S3_ENDPOINT_URL` / `S3_REGION` | 같은 이름 | `life-infra-map-media` / `http://127.0.0.1:9000` |
| **파일 공개 주소** | `S3_PUBLIC_DOMAIN` (스킴 없음) | `MEDIA_BASE_URL` (스킴 포함) | `127.0.0.1:9000/life-infra-map-media` |

마지막 항목은 **변수 이름과 형식이 다릅니다.** Django는 `S3_URL_PROTOCOL`과 `S3_PUBLIC_DOMAIN`을 합쳐 URL을 만들고, Spring은 `MEDIA_BASE_URL` 하나에 스킴까지 포함합니다. 한쪽만 바꾸면 업로드는 성공하는데 이미지 주소가 깨집니다.

### 이 구조에서 실제로 발생했던 문제

`JWT_SECRET`의 `application.yml` 기본값이 Django `.env` 값과 달랐던 적이 있습니다(`change-me-in-env-at-least-32-bytes-long`).

증상이 까다로웠습니다.

```text
Spring 로그인       성공 (토큰 정상 발급)
Django API 호출     401 — 서명 검증 실패
```

로그인이 되기 때문에 인증 설정 문제로 보이지 않고, 환경변수를 export 해 둔 셸에서는 재현되지 않습니다. 지금은 기본값을 맞춰 해결했지만, **새 설정값을 추가할 때마다 위 표에 추가하고 양쪽 기본값을 같게 두는 것**이 같은 문제를 막는 방법입니다.

### 배포 환경

기본값에 의존하지 말고 환경변수로 명시적으로 주입합니다. compose로 두 앱을 함께 띄우면 `environment:`에서 한 곳으로 모을 수 있습니다. 특히 `JWT_SECRET`과 `S3_SECRET_KEY`는 저장소에 있는 로컬 개발용 값을 그대로 쓰면 안 됩니다.

---

## 8. 스키마 소유권 규칙

**스키마의 주인은 Django입니다.** Spring은 Django가 만든 테이블에 매핑만 합니다.

`spring-api`의 `User.java` 주석에도 같은 내용이 있습니다.

```java
/**
 * Django 의 `auth_user` 테이블을 그대로 매핑합니다.
 *
 * 스키마 소유자는 Django 이므로 컬럼을 추가하거나 바꾸지 않습니다.
 * 바꿔야 하면 Django 마이그레이션으로 하고 여기 매핑을 맞춥니다.
 */
```

`ddl-auto: validate`가 이 규칙을 강제합니다. 매핑이 실제 스키마와 다르면 Spring이 부팅 단계에서 실패하므로, 불일치가 런타임까지 숨어 들어가지 않습니다.

### 컬럼을 추가해야 할 때의 순서

```text
1. Django 모델 수정
2. python manage.py makemigrations
3. python manage.py migrate
4. Spring 엔티티 매핑 추가
5. Spring 부팅으로 validate 통과 확인
```

순서를 바꾸면 안 됩니다. Spring 쪽을 먼저 고치면 `validate`에서 막혀 부팅되지 않습니다.

### 현재 매핑 확인 결과

`auth_user`의 실제 타입과 `User.java` 매핑이 일치합니다.

| 컬럼 | PostgreSQL | Java |
|---|---|---|
| `id` | `integer` | `Integer` |
| `password` | `varchar(128)` | `String` |
| `date_joined` | `timestamp with time zone` | `OffsetDateTime` |
| `last_login` | `timestamp with time zone` (nullable) | `OffsetDateTime` |

---

## 9. 인증을 공유하는 방식

두 서비스가 같은 사용자와 같은 토큰을 이해해야 합니다. 두 가지로 맞췄습니다.

### 9.1 비밀번호 해시 형식

Spring의 `DjangoPasswordEncoder`가 Django 형식의 해시를 그대로 읽고 씁니다.

```text
pbkdf2_sha256$1200000$salt$hash
```

덕분에 기존 Django 계정으로 Spring에서 로그인할 수 있고, Spring에서 만든 계정도 Django가 인식합니다.

### 9.2 JWT 공유 비밀키

Spring이 발급한 토큰을 Django도 검증합니다. `backend/accounts/authentication.py`의 `SharedJWTAuthentication`이 그 역할을 합니다.

| 항목 | 값 |
|---|---|
| 알고리즘 | HS256 |
| 클레임 | `sub`(사용자 id), `username`, `exp`, `iat` |
| 헤더 | `Authorization: Bearer <token>` |
| 비밀키 | `JWT_SECRET` — **양쪽이 같은 값이어야 합니다** (7.5 참고) |
| 유효 시간 | `JWT_ACCESS_MINUTES` 기본 120분 |

비밀키가 어긋나면 **로그인은 성공하는데 Django API만 401**이 되므로 원인을 찾기 어렵습니다. `application.yml` 기본값을 `backend/.env`와 같게 맞춰 두었습니다.

기존 DRF `TokenAuthentication`도 함께 남겨 두었습니다. Django 로그인을 쓰는 화면이 아직 있어서 이관이 끝날 때까지 두 방식을 모두 받습니다.

클레임을 바꾸면 Spring `JwtService`와 Django `SharedJWTAuthentication`을 함께 고쳐야 합니다.

---

## 10. 지켜야 할 규칙

- 스키마 변경은 **Django 마이그레이션으로만** 합니다.
- Spring의 `ddl-auto`는 **`validate` 외의 값으로 바꾸지 않습니다.** `update`로 두면 Hibernate가 Django 스키마를 변경해 마이그레이션 상태와 실제 스키마가 어긋납니다.
- `JWT_SECRET`은 양쪽이 같은 값을 씁니다.
- JWT 클레임을 바꾸면 양쪽을 함께 고칩니다.
- 개발용 DB는 **각자 로컬**에 띄웁니다. 팀 공용 DB를 쓰면 한 사람의 마이그레이션이 다른 사람의 Spring 부팅(`validate`)까지 깨뜨립니다.

---

## 11. 주의사항 및 남은 작업

| 항목 | 내용 |
|---|---|
| Spring이 슈퍼유저로 접속 중 | `life_infra_map` 역할이 superuser입니다. 현재는 `ddl-auto: validate`가 유일한 안전장치이며 설정 한 줄로 뚫립니다. 배포 전에 DDL 권한이 없는 별도 역할(`SELECT/INSERT/UPDATE/DELETE` + 시퀀스 `USAGE`만 부여)로 분리하는 것이 좋습니다. |
| 환경변수 이중 관리 | Django는 `.env`, Spring은 OS 환경변수를 읽습니다. 값이 어긋나면 서로 다른 DB를 보거나 토큰 검증에 실패합니다. 맞춰야 하는 값 목록은 7.5에 있습니다. |
| multipart 업로드 테스트 | 기본 회귀 테스트는 `StorageService`를 mock 처리해 회원가입·프로필 변경·게시글 이미지 업로드를 검증합니다. 실제 MinIO 저장은 별도 `integrationTest`로 분리했습니다. |
| 연결 수 | `max_connections=100`, Django `CONN_MAX_AGE=60` + HikariCP 기본 10이므로 로컬에서는 여유가 있습니다. |
| 배포 구성 | 배포·시연용 서버에는 DB와 앱을 함께 두어 네트워크 지연을 없앱니다. 개발용 공유 DB와는 다른 목적입니다. |

---

## 12. 검증 기록

| 확인 항목 | 결과 |
|---|---|
| Django 테스트 | 738개 실행, 실패 0 (21개 skip) |
| **Spring 테스트** | **103개 통과** |
| **Spring 부팅** | 성공 — `ddl-auto: validate`가 실제 Django 스키마를 통과 |
| **교차 인증** | Spring이 발급한 JWT를 Django `SharedJWTAuthentication`이 검증 성공. 클레임 `{sub, username, iat, exp}` 확인 |
| 프론트 라우팅 | `serviceRoutes.js`의 경로 분기, `Bearer` 헤더 전환, Spring 후행 슬래시 제거 동작 |

`ddl-auto: validate` 통과가 특히 중요합니다. Spring 엔티티가 Django 마이그레이션이 만든 스키마와 어긋나면 부팅 자체가 실패하므로, 부팅 성공은 두 서비스의 스키마 인식이 일치한다는 증거입니다.

### Spring 테스트 구성

`@SpringBootTest` + `MockMvc`는 `src/test/resources/application.yml`의 일회성 H2 데이터베이스를 사용하고 테스트마다 롤백합니다. 따라서 개발용·운영용 Postgres가 없어도 전체 회귀 테스트를 실행할 수 있습니다. 실제 PostgreSQL 스키마 호환성은 Spring 운영 부팅의 `ddl-auto: validate`와 배포 smoke test로 별도 확인합니다.

| 클래스 | 개수 | 범위 |
|---|---|---|
| `AuthApiTest` | 21 | 로그인·회원가입·내정보·비밀번호·닉네임·프로필·마이페이지·로그아웃 |
| `BoardApiTest` | 17 | 글·댓글·반응, 수정·삭제 권한, 비로그인 조회 |
| `AdminApiTest` | 18 | 관리자 권한 경계, 목록 응답 형태, 등급 조회 인증 |
| `UserDataApiTest` | 18 | 알림·문의·저장 장소의 사용자별 격리 |
| `ReportApiTest` | 12 | 신고 규칙(본인·중복), 처리 권한, 관리자 알림 |
| `MultipartUploadApiTest` | 5 | 이미지 업로드와 실패 요청의 업로드 선실행 방지 |
| `ApiContractCompatibilityTest` | 3 | Django식 스네이크 입력, 신고 PATCH 처리, 입력 검증 |
| `StorageServiceValidationTest` | 1 | 이미지 확장자로 위장한 비이미지 차단 |
| `ContributionRulesTest` · `DjangoPasswordEncoderTest` | 8 | 기여도 규칙, Django 해시 호환 |

### 테스트로 찾은 결함

이관 검증 중 테스트가 잡아낸 것들입니다. 모두 눈으로는 발견되지 않는 종류였습니다.

| 결함 | 증상 | 조치 |
|---|---|---|
| 인증 실패 시 403 (Django 는 401) | 토큰이 만료되면 프론트 인터셉터가 401 에서만 동작하므로, 토큰이 지워지지 않고 로그인 유도도 되지 않음 | `AuthenticationEntryPoint` 추가 |
| 문의·신고 목록을 페이지네이션으로 감쌈 | `AdminInquiryView`·`ReportListView` 가 `.map()` 을 호출해 `TypeError`, `MyInquiryView` 는 빈 목록 | 배열로 되돌림 |
| 문의 상세 접근 거부가 404 (Django 는 403) | 프론트가 보여 줄 메시지가 달라짐 | Django 와 같은 403·메시지로 맞춤 |
| `JWT_SECRET` 기본값 불일치 | 로그인은 되지만 Django API 만 401 | `application.yml` 기본값을 맞춤 |
| `/api/tiers/**` 전면 공개 | 인증 없이 남의 등급·기여도 조회 가능 | 인증 필요로 변경 |

### MinIO 통합 테스트

`MultipartUploadApiTest`는 `StorageService`를 mock 처리하므로 기본 Spring 회귀 테스트가 MinIO 상태에 의존하지 않습니다. 실제 저장소 연동은 `StorageServiceMinioIntegrationTest`가 파일 업로드·조회·콘텐츠 타입·정리까지 확인합니다.

루트에서 `docker compose up -d storage storage_init`으로 MinIO와 버킷을 준비한 뒤 다음처럼 별도로 실행합니다.

```powershell
cd spring-api
.\gradlew.bat integrationTest
```

---

## 13. 관련 문서

- `docs/02_data/postgres-migration.md` — PostgreSQL/PostGIS 전환 이유와 검증 결과
- `docs/02_data/pgadmin-guide.md` — DB 데이터를 브라우저에서 확인하는 방법
- `docs/02_data/db-seed-import-guide.md` — 새 환경에서 DB를 만들고 데이터를 적재하는 절차
