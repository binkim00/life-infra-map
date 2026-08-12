# pgAdmin으로 로컬 DB 보기

이 문서는 로컬 PostgreSQL 데이터를 브라우저에서 눈으로 확인하는 방법을 정리합니다.

MySQL Workbench처럼 테이블과 데이터를 화면으로 보기 위한 도구이며, 앱 동작과는 무관한 개발 편의 기능입니다.

pgAdmin은 컨테이너로 실행되므로 **로컬에 따로 설치할 프로그램은 없습니다.** PostgreSQL 서버도 컨테이너로 돌기 때문에 호스트에 PostgreSQL을 설치하면 오히려 5432 포트가 충돌합니다.

---

## 1. 실행

프로젝트 루트에서 실행합니다.

```bash
docker compose up -d db pgadmin
```

`db`가 healthy 상태가 된 뒤에 pgAdmin이 뜨도록 설정되어 있습니다.

처음 실행할 때는 이미지를 내려받고 초기화하는 시간이 필요하므로 화면이 열리기까지 20~30초 정도 걸릴 수 있습니다.

상태를 확인하려면 다음 명령어를 사용합니다.

```bash
docker compose ps
```

---

## 2. 접속

브라우저에서 아래 주소를 엽니다.

```text
http://localhost:5050
```

로컬 전용 설정이라 로그인 화면 없이 바로 들어갑니다.

좌측 트리에 **`life-infra-map (local)`** 서버가 이미 등록되어 있습니다. 서버를 처음 펼칠 때 비밀번호만 한 번 물어봅니다.

```text
Password: life_infra_map
```

**`Save password` 를 체크**하면 이후에는 다시 묻지 않습니다.

---

## 3. 데이터 확인 경로

트리에서 아래 순서로 펼치면 테이블 목록이 나옵니다.

```text
life-infra-map (local)
└── Databases
    └── life_infra_map
        └── Schemas
            └── public
                └── Tables
```

주요 테이블은 다음과 같습니다.

| 테이블 | 내용 |
|---|---|
| `recommendations_place` | 장소 |
| `recommendations_tag` | 태그 |
| `recommendations_placetag` | 장소-태그 연결 |
| `recommendations_placereport` | 오류 제보 |
| `recommendations_userpreference` | 사용자 선호 |
| `boards_post`, `boards_comment` | 게시글, 댓글 |
| `auth_user`, `accounts_userprofile` | 계정, 프로필 |

데이터를 보는 방법은 두 가지입니다.

- 테이블 우클릭 → `View/Edit Data` → `All Rows` : 그리드에서 값 확인 및 수정
- 상단 `Query Tool` : SQL 직접 실행

---

## 4. 접속 정보

pgAdmin 대신 DBeaver 같은 외부 도구를 쓰거나, 서버를 직접 등록해야 할 때 사용하는 값입니다.

| 항목 | 호스트에서 접속할 때 | pgAdmin 컨테이너에서 접속할 때 |
|---|---|---|
| Host | `127.0.0.1` | `db` |
| Port | `5432` | `5432` |
| Database | `life_infra_map` | `life_infra_map` |
| User | `life_infra_map` | `life_infra_map` |
| Password | `life_infra_map` | `life_infra_map` |

pgAdmin은 컨테이너 안에서 실행되므로 호스트명이 `127.0.0.1`이 아니라 compose 서비스명 `db`입니다. 포트도 호스트 매핑값이 아닌 컨테이너 내부 포트인 `5432`를 사용합니다. 이 부분에서 접속 실패가 자주 생기므로 주의합니다.

`.env`로 값을 바꾼 경우에는 바꾼 값을 사용합니다.

---

## 5. 설정 파일

| 파일 | 역할 |
|---|---|
| `docker-compose.yml` 의 `pgadmin` 서비스 | pgAdmin 실행 설정, 포트 |
| `docker/pgadmin/servers.json` | 접속 대상 서버 사전 등록 |

`.env`에서 조정할 수 있는 값은 다음과 같습니다.

```text
PGADMIN_PORT=5050
```

5050 포트를 이미 쓰는 프로그램이 있으면 이 값을 바꿉니다.

---

## 6. 중지 및 초기화

```bash
docker compose stop pgadmin     # pgAdmin만 중지
docker compose down             # 전체 중지 (데이터는 남음)
```

`servers.json`은 **최초 실행 때 한 번만 읽힙니다.** 내용을 수정한 뒤 다시 반영하려면 pgAdmin 설정 볼륨을 삭제하고 다시 실행합니다.

```bash
docker compose down
docker volume rm life-infra-map_pgadmin_data
docker compose up -d db pgadmin
```

이 볼륨에는 pgAdmin 자체 설정만 들어 있고 장소 데이터는 들어 있지 않으므로, 삭제해도 DB 데이터에는 영향이 없습니다.

---

## 7. 문제가 생겼을 때

| 증상 | 확인 사항 |
|---|---|
| 페이지가 안 열림 | 초기화에 시간이 걸립니다. `docker logs life-infra-map-pgadmin` 으로 기동 여부를 확인합니다. |
| 서버 트리가 비어 있음 | `servers.json`이 최초 실행 때만 읽힙니다. 6번 항목의 볼륨 삭제 절차를 따릅니다. |
| 서버 연결 실패 | Host를 `127.0.0.1`로 두지 않았는지 확인합니다. 컨테이너 안에서는 `db`입니다. |
| 포트 충돌 | `.env`의 `PGADMIN_PORT`를 다른 값으로 바꿉니다. |

---

## 8. 설치형 도구를 쓰는 경우

컨테이너를 띄우지 않고 데스크톱 앱으로 보고 싶으면 DBeaver Community를 사용할 수 있습니다.

```bash
winget install dbeaver.dbeaver
```

접속 정보는 4번 표의 **호스트에서 접속할 때** 열을 사용합니다.

PostgreSQL과 SQLite를 한 창에서 볼 수 있으므로, 기존 `backend/db.sqlite3` 데이터와 비교할 때 유용합니다.

---

## 9. GUI 없이 확인하기

터미널에서 바로 확인할 수도 있습니다.

```bash
docker exec -it life-infra-map-db psql -U life_infra_map -d life_infra_map
```

```text
\dt              -- 테이블 목록
\d 테이블명       -- 테이블 구조
\q               -- 종료
```

Django 설정 기준으로 접속하려면 다음 명령어를 사용합니다.

```bash
cd backend
python manage.py dbshell
```

---

## 10. 주의사항

- pgAdmin은 로컬 개발 전용입니다. 로그인과 마스터 패스워드 단계를 끈 상태이므로 **5050 포트를 외부에 노출하지 않습니다.**
- 위 접속 정보는 로컬 기본값입니다. 배포 환경에서는 사용하지 않습니다.
- 그리드에서 데이터를 직접 수정하면 Django 모델 검증과 `updated_at` 갱신을 건너뛰게 됩니다. 확인 목적으로 사용하고, 실제 데이터 변경은 Django 명령어나 관리자 화면을 사용합니다.
