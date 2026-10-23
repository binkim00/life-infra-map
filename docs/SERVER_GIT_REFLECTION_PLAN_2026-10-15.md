# 서버 코드 Git 반영 후보 검토 — 2026-10-15

최신 원격 브랜치 12개의 끝 커밋과 이력을 비교했다. 서버 파일을 Git으로 덮어쓰거나 DB·서비스·실행 설정을 변경하지 않았다. 커밋·푸시·배포도 수행하지 않았다.

## 비교 기준

- 서버 작업 폴더: `/home/ubuntu/life-infra-map/app`.
- 원격 `master`: `c58d885c52ddf65095e1d28efb0fdc4015e6b9ba`.
- 비교 브랜치: `master`, `kyb`, `practice`, `codex/account-deletion-race`, `codex/collection-freshness-filter`, `codex/collection-p0-telemetry`, `codex/collection-resource-budget`, `codex/disk-maintenance`, `codex/mobile-draft-photo-followup`, `codex/release-foundation`, `codex/release-infra`, `codex/remaining-contract-ux-integration`.
- 기존 14개 후보의 서버 원본 해시가 앞선 조사 이후 바뀌지 않았음을 확인했다. 같은 경로의 브랜치 끝·과거 이력을 비교한 뒤 다른 경로의 동일 Git 객체와 Git LFS 포인터도 확인했다.
- 근거 파일: `runtime/server-git-audit-20261015/remote-branches.json`, `all-branch-comparison.json`, `server-source-audit.json`, `server-files/`, `patches/`.

## 기존 14개 후보의 최종 분류

| 파일 | 판단 | Git 반영 방향 |
| --- | --- | --- |
| `backend/recommendations/fixtures/loaddata/tags.json` | LFS 객체 SHA-256와 실제 서버 파일이 일치 | 이미 보관됨. 새 데이터로 다시 추가하지 않음 |
| `backend/recommendations/map_search.py` | 동일 내용이 `backend/recommendations/services/map_search.py`로 게시된 이력에 존재 | 옛 경로에 중복 추가하지 않음 |
| `backend/recommendations/services/ai_search_orchestrator.py` | 서버에는 master의 후보 신원 결합·검색 계측·근거 후보 보완 등이 빠져 있음 | 서버 파일 전체 반영 제외. 필요하면 개별 변경 의도를 별도 검토 |
| `backend/recommendations/services/search_hard_gate.py` | 서버와 master의 웹 근거 승인·신뢰 판정 규칙이 다름 | 사용자 결과 판정이 바뀌므로 자동 반영 제외 |
| `backend/recommendations/views.py` | 서버는 제보 전용 serializer 등을 사용하지 않는 사본이며 버전 충돌 검사 순서도 다름 | 최신 제보 처리 변경을 되돌리는 전체 덮어쓰기 제외 |
| `frontend/src/views/home/PlaceResultList.jsx` | 서버는 카테고리 표시 변환 대신 원래 카테고리 값을 직접 출력 | 최신 표시 처리를 되돌리는 전체 덮어쓰기 제외 |
| `deploy/observability/compose.json` | 모든 원격 브랜치 이력에 동일 내용 없음. 로컬 후보와 운영 파일 SHA-256 일치 | 로그 수집 구성 반영 후보 |
| `deploy/observability/compose.metrics.json` | 위와 같음 | 자원 수집 구성 반영 후보 |
| `deploy/observability/loki.json` | 위와 같음 | 로그 보관 구성 반영 후보 |
| `deploy/observability/prepare.py` | 위와 같음 | 정제·프로비저닝 생성 도구 반영 후보 |
| `deploy/observability/install_metrics.py` | 위와 같음 | 자원 그래프 설치·검증 도구 반영 후보 |
| `deploy/observability/db_fingerprint.py` | 위와 같음 | 이전 검증 도구로 별도 반영 후보 |
| `deploy/observability/prepare_clone.py` | 위와 같음 | 오프라인 복제 준비 도구로 별도 반영 후보 |
| `deploy/observability/prometheus.json` | 설치 도구가 생성하는 설정이며 로컬 `.gitignore`에도 제외됨 | 생성물을 직접 커밋하지 않음 |

LFS 확인값: `tags.json`의 실제 파일 SHA-256은 `4f8f3e12167ba0db878469828fa1abb61e34089c7f57a30b9ce6e0aaff6b645c`, Git LFS 포인터의 크기는 30,507바이트다. `map_search.py`와 일치한 게시 객체는 `e66c47666bb304f19dbfa6ac50fd1c94d5ea3d5a`이며 `master`를 포함한 10개 브랜치의 이력에 있다.

따라서 앞선 “14개 모두 추가 보존이 필요한 코드”라는 해석은 정확하지 않다. 2개는 이미 Git/LFS에 있고, 4개는 전체 반영하면 현재 master 동작을 되돌릴 수 있는 차이이며, 1개는 생성 설정이다. 나머지 7개 원본이 새 반영 후보이다. 이 판단은 코드 정적 비교이며 검색 기능 회귀 테스트 결과를 뜻하지 않는다.

## 권장 커밋 구성

### 1. Grafana·Loki·서버 자원 그래프 구성

다음 7개를 한 단위로 검토한다.

- `deploy/observability/compose.json`
- `deploy/observability/compose.metrics.json`
- `deploy/observability/loki.json`
- `deploy/observability/prepare.py`
- `deploy/observability/install_metrics.py`
- `deploy/observability/.gitignore`
- `deploy/observability/README.md`

기존 14개에 없던 `.gitignore`·README는 안전한 제외 규칙과 사용·설치 절차를 함께 보관하기 위한 동반 파일이다. 앞선 설치에서 실제 로그 조회와 자원 8개 패널 검증은 완료됐으며, 이번에는 재설치하지 않았다. 이미지 digest 기록은 런타임에 보관돼 있으므로 Git 반영 시에도 실제 검증한 digest의 보관 방법을 함께 명시한다.

### 2. 서버 이전·복구 검증 도구와 기록

운영 모니터링 설치와 분리해 다음 4개를 검토한다.

- `deploy/observability/db_fingerprint.py`
- `deploy/observability/prepare_clone.py`
- `deploy/observability/mount_clone.py`
- `deploy/observability/MIGRATION.md`

도구에는 해당 이전 작업의 경로·컨테이너 수·인스턴스/네트워크 전제가 있다. 일반 운영 서버에서 자동 실행되는 도구로 취급하지 않고, 기록된 오프라인 준비 절차와 함께 보관한다.

## 제외 범위와 남은 한계

- `.env`, `.env.metrics`, 관리자 비밀번호·키, `config.alloy`, 생성 프로비저닝, `prometheus.json`, DB·런타임 자료는 커밋 목록에서 제외한다.
- 서버의 검색 관련 4개 사본을 master에 통째로 덮어쓰지 않는다. 반대로 이번 조사로 운영 서버를 master에 맞춰 배포하지도 않는다.
- 다른 채팅의 backend·mobile·문서 변경은 이번 반영 후보와 분리한다.
- 비교는 Git 작업 폴더 사본 기준이다. 실행 중인 컨테이너 이미지 내부와 별도 release 폴더가 같은 코드인지는 이번 범위에서 검사하지 않았다.
- 공유 체크아웃에 `add`·커밋·푸시를 하지 않았다. 실제 반영 단계에서는 위 목록만 분리해 검토하고 관련 검사 후 게시한다.
