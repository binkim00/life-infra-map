# Grafana·Loki 도입 구성

상태: 운영 서버 읽기 전용 진단과 구성 설계 완료. 설치·배포·서비스 재시작·클라우드 리소스 생성 없음.

## 직접 확인한 운영 상태

2026-10-14 14:59 KST부터 AWS SSM으로 현재 온라인 Ubuntu 서버를 조회했다. 원문 로그·환경 변수·인증정보는 출력하거나 저장하지 않고 서버 안에서 형식, 필드명, 건수와 바이트만 집계했다.

| 항목 | 실측 |
| --- | --- |
| RAM 전체 / MemAvailable | 1.86 GiB / 725 MiB |
| Swap 전체 / 사용 | 2 GiB / 798 MiB |
| 루트 디스크 전체 / 사용 / 여유 | 37.70 / 26.82 / 10.87 GiB |
| 실행 컨테이너 | 8개 |
| Docker 이미지 / 빌드 캐시 | 9.124 GB / 6.335 GB |
| load average, 1/5/15분 | 0.25 / 0.19 / 0.18 |

vmstat의 두 번째·세 번째 1초 표본에서 swap-in/out은 0이었다. 현재 스왑 사용은 확인되지만 이 짧은 표본으로 지속적인 메모리 부족이나 피크 여유를 확정하지 않는다. CPU 사용률은 한 시점의 값이며 장기 부하 자료가 아니다. 캐시·이미지·데이터 삭제는 하지 않았다.

실측 컨테이너 메모리: DB 251 MiB, Spring 141.4 MiB, Django 90.5 MiB, scheduler 85.57 MiB, storage 68.14 MiB, worker 41.1 MiB, public-edge 16.77 MiB, gateway 2.031 MiB.

## 로그 형태와 수집 대상

모든 실행 컨테이너는 Docker `json-file` 드라이버이며 개별 LogConfig.Config는 빈 객체다. Docker 외부 JSON 봉투와 애플리케이션 메시지 내부 JSON은 별개다. 개별 회전 옵션은 확인되지 않았으며 Docker daemon 전역 설정은 이번에 조회하지 않았다.

| 서비스 | 실측 형식 | 지난 24시간 조회 줄 / UTF-8 바이트 | 도입 범위 |
| --- | --- | --- | --- |
| tag-scheduler | 일반 텍스트 + `collection_metrics {JSON}` | 1,359 / 372,010 | 1차 |
| tag-worker | `collection_metrics {JSON}` | 1,805 / 525,887 | 1차 |
| gateway | HTTP access 일반 텍스트 | 6,066 / 540,890 | 1차, 정제 후 |
| django-api | HTTP access 일반 텍스트 | 5,625 / 672,766 | 1차, 정제 후 |
| spring-api | 지난 24시간 출력 0 | 0 / 0 | 1차, 형식은 추가 확인 |
| public-edge | 표본 10줄 모두 JSON 시작 | 10 / 2,888 | 2차 |
| storage | 지난 24시간 출력 0 | 0 / 0 | 2차, 형식 미확인 |
| runtime-db | 일반 텍스트 | 600 / 128,972 | 초기 제외 |

24시간 조회는 서비스별 tail 10,000줄 상한에 도달하지 않았다. 조회 가능한 현재 컨테이너 로그 합계는 15,465줄, 2,243,413바이트(약 2.14 MiB)다. 컨테이너 재생성·기존 회전으로 이미 사라진 로그까지 포함하는 일일 발생량 증거는 아니다. 향후 트래픽 증가·장애 폭증·Loki 인덱스/WAL 비용을 이 값으로 예측하지 않는다.

worker에는 `worker_attempt`, `worker_checkpoint`, `worker`가, scheduler에는 `planner`, `scheduler_queue`, `scheduler`가 관찰됐다. `recorded_at`, `timings_ms`, `quality_at_save`, `requests`, `evidences`, `queue_depth` 등이 실제 존재한다. 수집 처리 성공과 긍정 근거 확보는 다른 지표로 표시한다.

gateway 최근 200줄에서 민감 필드명 흔적 3줄, URL 쿼리 흔적 2줄이 관찰됐다. 동일 줄 중복 가능성이 있으며 실제 값 유출을 확정한 수치는 아니다. 원문은 반환하지 않았다.

## 권장 배치: 운영 서버 수집기 + 분리된 모니터링 서버

```mermaid
flowchart LR
  A[운영 Docker 로그] --> B[Alloy: 정제·수집]
  B -->|사설망| C[Loki: 7일 보관]
  C --> D[Grafana: 관리자 대시보드]
```

현재 2 GiB급 운영 서버에 Grafana·Loki까지 동시 설치하는 안은 채택하지 않는다. 자원 제한으로 프로세스를 억지로 넣어도 피크 부하·쿼리·압축 작업 여유는 보장되지 않는다.

| 위치 / 구성요소 | 초기 설계 예산 | 연결 |
| --- | --- | --- |
| 기존 운영 서버 / Alloy | 메모리 상한 128 MiB, CPU 0.25, 상태·버퍼 공간 예산 256 MiB | 지정 5개 컨테이너만 수집 |
| 별도 모니터링 서버 / Loki 단일 프로세스 | 메모리 상한 768 MiB, CPU 0.5 | 내부 3100 |
| 별도 모니터링 서버 / Grafana | 메모리 상한 256 MiB, CPU 0.25 | loopback 3300 → SSH 또는 사설망 접속 |

별도 서버의 시작 설계는 2 vCPU / RAM 4 GiB / 디스크 40 GiB다. 수치는 실측 소요량이나 성능 보장이 아닌 설치 후 조정할 초기 예산이다. 서버 생성·요금 발생은 이번 범위에 포함되지 않는다. 기존 관리용 서버가 있으면 우선 재사용하고, 관리형 Grafana/Loki를 선택하면 저장 위치·비용·로그 전송 대상을 별도로 정한다.

Alloy는 Docker 파일 로그를 읽기 전용으로 수집하는 `loki.source.file` 방식부터 구성한다. 대상 컨테이너의 inspect LogPath를 설치 시 정확히 매핑하고 Docker JSON을 먼저 해제한다. Docker socket은 초기 설계에서 마운트하지 않는다. Docker 로그 경로를 읽을 수 있는 제한된 수집 권한이 필요하며 원본 로그를 수정하지 않는다. 컨테이너 재생성으로 LogPath가 바뀌면 배포 절차에서 대상 매핑을 다시 생성·검증해야 한다. 무작위 컨테이너 로그를 광범위하게 자동 수집하지 않는다.

Alloy reader 위치 상태는 영속화한다. 파일 회전·재생성·수집기 재시작 시 유실/중복은 설치 검증 항목이며 현재 보장하지 않는다. 목적지가 장시간 끊기면 메모리 큐나 위치 저장만으로 무손실을 보장할 수 없다. 제한된 WAL 사용 여부와 버전별 동작은 구현 시 검증하고, 원본 Docker 로그 보존 구간 안의 재수집 절차를 둔다.

## 파싱·개인정보·보존 정책

1. 공통 라벨은 `environment=production`, `service`만 기본 사용한다. collection 로그에 한해 제한된 `component`를 추가한다. 날짜·장소 ID·작업 ID·URL·검색어·IP는 라벨로 만들지 않는다.
2. collection 로그는 접두사 제거 → JSON 파싱 → 안전 필드 허용 목록으로 재구성한다. 원본 검색어·근거 본문·장소 식별자는 전송하지 않는다. `recorded_at`을 이벤트 시각으로 해석하고 파싱 실패 건수를 별도로 센다.
3. HTTP 로그는 시간·서비스·메서드·정규화된 경로·상태 코드·바이트 수를 추출한 새 메시지만 전송한다. 쿼리 문자열·IP·referer·user-agent·cookie·authorization·요청/응답 본문은 제외한다. 형식을 해석하지 못한 access 줄은 원문 전달 대신 drop 카운터로 남긴다.
4. Spring 예외는 형식 확인 후 멀티라인 결합·민감정보 제거를 검증한다. 초기 미확인 형식의 원문은 무조건 전달하지 않는다. DB는 SQL과 사용자 데이터 가능성이 있어 초기 제외한다.
5. Loki는 TSDB + filesystem, replication factor 1, 24h index period, Compactor retention 활성화, `retention_period=168h`(7일)로 설계한다. 단일 서버이므로 HA나 백업 보장을 주장하지 않는다. 사용자 접근은 Grafana 인증을 거치며 Loki는 인터넷에 공개하지 않는다.
6. Loki 디스크 예산은 우선 5 GiB이며 이는 하드 제한이 아니다. 사용량 4 GiB 또는 호스트 여유 10 GiB 미만에서 점검, 5 GiB 또는 여유 5 GiB 미만이면 수집 중단·원인 확인 기준으로 둔다. 시간 기반 retention은 공간 상한을 보장하지 않으며 chunk 삭제는 비동기다. DB/기존 백업을 삭제하는 자동 정리는 넣지 않는다.
7. Docker 로그 회전은 daemon 전역 설정 확인 후 `max-size=10m`, `max-file=3`을 서비스별 차기 배포 후보에 반영한다. 기존 컨테이너 즉시 재생성은 이번에 하지 않는다. 회전 설정 적용과 기존 로그 수집 여부를 따로 검증한다.

## 최초 대시보드

- 서비스별 정제 로그 탐색과 오류 건수. access 로그의 응답 시간은 현재 실측 필드 존재를 확인하지 않았으므로 초기 패널에서 제외한다.
- `worker_attempt`의 status별 건수·requests·evidences·new_evidences·timings_ms. checkpoint나 sleep 이벤트를 작업 완료 횟수에 중복 합산하지 않는다.
- scheduler_queue의 queue_depth는 합계 대신 마지막 값으로 표시한다. planner의 scanned/unique_candidates와 제외 사유는 planner 이벤트만 집계한다.
- 수집량·정제 실패/drop·전송 오류. 로그 0건을 서비스 장애로 단정하지 않는다. 기존 CloudWatch 상태/heartbeat 경보는 유지한다.
- CPU·RAM·디스크의 지속 시계열은 Loki 로그만으로 새로 생기지 않는다. 이번 도입은 로그가 대상이며, 자원 그래프가 필요하면 기존 CloudWatch 연동이나 별도 metrics 수집을 후속으로 정한다.

## 배포 전과 완료 기준

- 목적지 서버를 정한 후 `deploy/observability/`에 버전 고정 Compose, Loki, Alloy, Grafana datasource/dashboard 설정을 작성한다. 인증정보는 소스나 문서에 저장하지 않는다.
- 합성 로그로 Docker 봉투·접두 JSON·access·멀티라인 파싱, 민감 필드 제거, 오류/drop 카운터와 라벨 수를 검증한다.
- 목적지에서 설정 검증·Loki ready·Grafana datasource 조회·7일 retention 설정과 영속 볼륨을 확인한다.
- 운영 Alloy 추가 후 기존 서비스 상태와 실제 정제 이벤트 1건의 Grafana 조회까지 확인한다. 메모리 128 MiB 한도·OOM·기존 서버 MemAvailable 512 MiB 미만 여부를 확인하고 문제가 생기면 수집기만 중지한다. 512 MiB는 운영 정책 제안이며 기존 자동 경보가 아니다.
- 회전·재시작·목적지 단절/회복의 중복·유실·버퍼 한도를 별도로 검증한다. 온라인 조회 성공을 이 검증의 대체로 삼지 않는다.

읽기 전용 감사 SSM 명령: `ece0fad1-e8e2-4722-9a84-adbe0b5eb287`, `d211fa7a-f293-4676-9ece-a5ae22f475d2`; 둘 다 Success, stderr 없음.

다음 한 가지 행동: 모니터링 목적지(재사용 가능한 별도 서버 또는 새 서버)를 확정한 뒤 위 설계를 배포 파일로 구체화한다.

## 공식 참고 자료

- [Alloy 파일 로그 수집](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.file/)
- [Alloy 로그 처리](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.process/)
- [Loki 보존 정책](https://grafana.com/docs/loki/latest/operations/storage/retention/)
- [Loki 저장 구성](https://grafana.com/docs/loki/latest/configure/storage/)
