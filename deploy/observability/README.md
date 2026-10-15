# LifeMap 로그 화면

2026-10-15 운영 연결: 서울 2b의 `i-04208c6e8df9328d9` (`c7i-flex.large`, RAM 4GiB).
Tailscale 연결 후 [Grafana 로그인](http://100.71.169.91:3300/login)에서 `admin` 계정으로 접속한다.
초기 비밀번호는 새 서버의 `/home/ubuntu/life-infra-map/app/deploy/observability/secrets/grafana-admin` 파일에만 보관한다.
대시보드는 `LifeMap 서비스 로그` (`lifemap-logs`)이며 실제 5개 서비스의 정제 로그 조회를 검증했다.
서버와 사용자 PC 양쪽에서 로그인 화면의 HTTP 200을 확인했다.

사용 방법:

1. PC에서 Tailscale을 연결하고 위 로그인 화면을 연다.
2. 초기 비밀번호는 서버 터미널에서 아래 명령으로 직접 확인한다. 화면 공유·채팅·Git에는 붙여넣지 않는다.

   ```sh
   sudo cat /home/ubuntu/life-infra-map/app/deploy/observability/secrets/grafana-admin
   ```

3. Dashboards에서 `LifeMap 서비스 로그`를 열고 시간 범위를 최근 15분 또는 1시간으로 선택한다.
4. Explore에서 `LifeMap Loki`를 선택하면 아래 검색식을 사용할 수 있다. Loki는 로그 저장·검색을 담당하며 사용자는 Grafana에서 조회한다.

| 보고 싶은 내용 | 검색식 |
| --- | --- |
| 전체 운영 로그 | `{environment="production"}` |
| 태그 수집 작업 | `{service="tag-worker"}` |
| 스케줄러 | `{service="tag-scheduler"}` |
| Spring 오류 수준 | `{service="spring-api"} | json | level="ERROR"` |
| 게이트웨이 5xx 응답 | `{service="gateway"} | json | status=~"5.."` |

바탕화면 `life-infra-map EC2`는 VS Code, `여기일지도 서버`는 MobaXterm 서버 접속용이다. 두 연결 모두 Tailscale 주소 `100.71.169.91`을 사용한다. 일반 앱 실행용 `Visual Studio Code`·`MobaXterm` 아이콘은 그대로 유지했다.

서버 자원은 [LifeMap 서버 자원](http://100.71.169.91:3300/d/lifemap-host)에서 본다.
로그인 후 Dashboards에서 같은 이름을 선택해도 된다. CPU·메모리 사용률, 루트 디스크 사용률·남은 공간, 스왑 사용량, 네트워크 수신·송신, 서버 부하 8개 패널이 있다. 30초마다 수집·갱신하며 설치 이후 기록부터 표시한다. 네트워크는 호스트 인터페이스별 값이고 컨테이너별 자원 그래프는 포함하지 않는다.

추가 구성은 `compose.metrics.json`의 Prometheus(192MiB 상한)·Node Exporter(64MiB 상한)다. 실제 초기 메모리 합계는 약 33MiB였다. Prometheus는 호스트 포트를 공개하지 않고, exporter는 Docker 내부 주소 `172.17.0.1:19100`에만 수신한다. 호스트 마운트는 읽기 전용이다. 공식 이미지의 실제 digest는 서버 `runtime/host-metrics-20261015/images.json`에 고정하며, `.env.metrics`로 기존 로그 구성과 분리한다. 기존 컨테이너를 재생성하지 않는다.

자원 기록은 7일, 저장 블록은 512MiB 보관 기준이다. WAL·메모리 내 최신 데이터 등은 블록 기준과 별도이므로 전체 디스크 사용량의 엄격한 상한을 뜻하지 않는다. 설정·검증 기록은 같은 runtime의 `before.json`·`verification.json`에 있다. 새 설치의 첫 두 scrape가 쌓이기 전에는 CPU·네트워크 그래프가 비어 있을 수 있다.

SSH와 권한 확인:

```sh
# PC 터미널에서 서버 접속
ssh lifemap-ec2
# 접속 후 현재 계정, 그룹, 관리자 실행 권한 확인
whoami
id
sudo -l
# 특정 폴더의 소유자와 접근 권한
ls -ld /home/ubuntu/life-infra-map/app
```

현재 `ubuntu` 계정은 `sudo`·`docker` 그룹에 속하며 `sudo -l`에서 비밀번호 없는 관리자 실행 권한을 확인했다. PEM의 개인키로 SSH 인증을 수행한 뒤 실제 파일·명령 접근은 로그인한 Linux 계정의 권한으로 결정된다.

이 구성은 기존 DB·앱 컨테이너를 재생성하지 않고 별도 Grafana·Loki·Alloy를 추가한다. Loki는 7일 보관하며 인터넷에 공개하지 않는다. Grafana는 loopback 또는 확인된 Tailscale 주소의 3300 포트에서만 연다. CloudWatch 기존 경보는 유지한다.

`prepare.py`는 서버에서 실행하며 공식 이미지의 실제 RepoDigest를 기록한 `monitoring-images.json`을 입력받는다. 최신 태그 자체로 배포하지 않고 조회된 digest로 고정한다. 초기 관리자 비밀번호는 서버의 `secrets/grafana-admin`에만 생성하고 출력하지 않는다. `.env`, secret, 수집 대상 경로는 Git에 포함하지 않는다.

수집 대상은 worker·scheduler·gateway·Django·Spring이다. DB와 사용자 원문은 수집하지 않는다. collection JSON은 허용 필드만 재구성하고, HTTP는 메서드·상태 코드만, Spring은 로그 수준만 저장한다. 요청 URL·검색어·IP·cookie·본문·원문 예외는 제외한다. 이는 최초 안전 수집 범위이며 전체 예외 스택 추적은 별도의 정제 검증 후 확장한다.

서비스를 재생성해 컨테이너 ID가 바뀌면 `prepare.py`로 로그 경로를 갱신하고 Alloy만 재시작한다. 서버 중지·시작만으로는 ID가 바뀌지 않는다. 위치 상태는 별도 runtime 디렉터리에 유지한다. 장시간 전송 장애의 무손실 보장은 아직 검증하지 않았다.

배포 순서:

1. 기존 서비스와 DB 복구를 먼저 확인한다.
2. 확인된 사설 주소로 `prepare.py --images <서버 이미지 기록> --bind-ip <주소>`를 실행한다.
3. `docker compose -f compose.json config --quiet`, Loki config 검증, Alloy config 검증을 통과시킨다.
4. 합성 로그의 원문·민감 필드 제거와 실제 worker 이벤트의 Loki 조회를 확인한다.
5. Grafana datasource health와 `lifemap-logs` 대시보드 조회, 기존 DB·서비스 상태와 디스크 여유를 다시 확인한다.

3개 구성요소의 메모리 상한 합계는 1,152MiB다. 시간 기반 보관은 디스크 용량 상한이 아니므로 기존 디스크 경보와 함께 실제 증가량을 확인한다. 문제가 발생하면 이 Compose만 중지하고 기존 앱·DB는 유지한다.
