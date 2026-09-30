# 수동 선별 배포 절차

이 절차는 운영 서버가 Git checkout이 아닌 현재 구조를 위한 것이다. 명시적으로
선택한 파일만 한 번에 반영한다. 이 문서를 준비했다고 운영 배포가 실행되지는 않는다.

## 1. 배포 대상 확정

1. GitHub Actions에서 배포할 **40자리 커밋 SHA의 CI 실행**이 성공했는지 화면에서
   확인하고 실행 번호와 링크를 기록한다. `--ci-run` 값은 기록용이며 도구가
   GitHub의 성공 여부를 대신 확인하지 않는다.
2. 마지막으로 운영에 반영한 파일 목록·해시와 후보 커밋의 변경 파일을 대조한다.
   운영 서버는 Git 저장소가 아니므로 로컬 브랜치의 앞뒤 관계만으로 운영 기준을
   추정하지 않는다. 삭제 파일, DB migration, 환경 변수, 비밀값, 권한 변경이
   포함되면 이 절차를 중지하고 별도 전환·복구 계획을 세운다.
3. 배포할 서비스와 정확한 파일을 적는다. 웹 파일 또는 `deploy/gateway/`의 변경은
   gateway, `backend/`는 django_api, `spring-api/`는 spring_api를 재빌드한다.
   `deploy/public-edge/`의 변경은 Caddy 설정 검증·재시작이 별도로 필요하다.
   다른 서비스·worker까지 영향이 있으면 그 범위를 먼저 명시한다.

로컬에서 선택 파일만 묶는다.

```powershell
python deploy/release/prepare_release.py `
  --commit <CI가 통과한 40자리 SHA> `
  --ci-run <성공한 Actions 실행 번호> `
  --output <새 ZIP 절대경로> `
  --file backend/path/to/changed.py `
  --file spring-api/path/to/changed.java
```

출력된 ZIP SHA-256, 커밋, CI 실행 번호, 파일 목록을 배포 기록에 보관한다.
도구는 명시한 커밋의 추적 파일 바이트를 읽으며 현재 작업 폴더의 수정 파일은
묶지 않는다. `.env`, 키·인증서·비밀값 경로는 허용하지 않는다.

## 2. 운영 전 안전 확인

- 최근 S3 PostgreSQL 백업의 업로드 결과와 **격리 복원 결과**를 확인한다.
  백업 객체가 존재한다는 사실만으로 복원 가능하다고 판단하지 않는다.
- 디스크 여유, 현재 컨테이너 건강 상태, 공개·사설 상태 API, 현재 이미지 ID,
  Compose 실행에 사용 중인 환경 파일 경로를 기록한다. 환경 파일 값은 출력하거나
  패키지에 넣지 않는다. 빌드 공간이 부족하면 중단한다.
- 변경할 각 파일의 현재 SHA-256을 기록하고 이전 배포 기록과 대조한다. 알 수 없는
  서버 수정이 있으면 덮어쓰지 않는다.
- 배포 직후 확인할 기능을 지정한다. 최소 게이트는 Caddy/Nginx 설정 검사,
  변경 서비스 건강 상태, 공개 HTTPS와 사설 상태 API, 변경 기능의 핵심 요청이다.
  로그인·게시물 같은 쓰기 흐름은 승인된 테스트 계정과 범위에서만 검증한다.

## 3. 파일 반영

기존의 신뢰된 전송 경로로 ZIP과 이 디렉터리의 `apply_release.py`를 서버에
전송한다. 서버에서 ZIP과 `apply_release.py`의 SHA-256이 로컬에서 기록한 값과
각각 같은지 확인한다. 서버 앱 루트는
`/home/ubuntu/life-infra-map/app`, 백업은 그 밖의
`/home/ubuntu/life-infra-map/release-backups/<고유 배포 ID>`에 둔다.

```bash
sha256sum <전송된 ZIP>
python3 apply_release.py \
  --root /home/ubuntu/life-infra-map/app \
  --backup /home/ubuntu/life-infra-map/release-backups/<고유 배포 ID> \
  --archive <전송된 ZIP>
```

기본 실행은 **읽기 전용 사전 점검**이다. 출력의 파일별 이전 해시·새 해시와
서비스 범위를 검토한 뒤에만 같은 명령에 `--apply`를 붙인다. 적용 시 파일별
원본을 백업하고 해시가 맞는 파일을 교체하며 `receipt.json`을 남긴다.
프로그램이 파일 교체 중 실패하면 그 실행에서 바꾼 파일을 복원한다.
백업 디렉터리가 이미 있으면 재사용하지 않고 중단한다.

## 4. 서비스 갱신과 검증

1. 운영에서 사용 중인 **정확한 env-file 인수**로 선택 서비스의
   `docker compose config --quiet`를 먼저 실행한다. 이 인수를 추정하거나
   비밀값을 로그에 복사하지 않는다. Nginx/Caddy 설정이 바뀌면 해당 설정 검사를
   추가한다.
2. 한 서비스씩 `docker compose up -d --no-deps --build <서비스명>`을 실행한다.
   서비스명은 `django_api`, `spring_api`, `gateway` 중 검토한 대상만 쓴다. gateway는 프런트엔드를
   이미지 안에서 빌드하므로 웹 변경도 gateway 재빌드가 필요하다. 데이터베이스,
   storage, worker는 변경 범위에 없으면 재생성하지 않는다.
3. 각 서비스가 healthy인지 확인한 뒤 다음 서비스를 갱신한다. 마지막에 공개
   `https://yeogiljido.com/gateway-health`, Django
   `/django/api/recommendations/health/`, Spring `/spring/api/health`,
   사설 `127.0.0.1:3000/gateway-health`와 변경 기능을 검증한다.
   실제 경로·응답 코드는 갱신 전 기준값과 대조한다.
4. 커밋, CI 링크, ZIP·파일 해시, 백업 경로, Compose 명령, 이전/새 이미지 ID,
   각 검사 결과를 배포 영수증에 기록한다. 모든 검사가 통과하기 전에는 완료로
   표시하지 않는다.

## 5. 실패 시 복구

검사 실패 시 해당 서비스의 추가 배포를 멈춘다. 새 파일이 그 뒤 수정되지 않았는지
도구가 확인한 다음 소스 파일을 원본으로 되돌린다.

```bash
python3 apply_release.py \
  --root /home/ubuntu/life-infra-map/app \
  --backup /home/ubuntu/life-infra-map/release-backups/<고유 배포 ID> \
  --rollback
```

그 후 변경했던 서비스를 **기록해 둔 기존 환경 파일·Compose 인수**로 다시 빌드·
재생성하고 동일한 상태·기능 검사를 반복한다. 파일이 배포 후 다시 변경됐거나
백업 해시가 다르면 도구는 덮어쓰지 않고 중단한다. DB를 초기화하거나 migration을
역적용하지 않는다. 복구 빌드가 실패하면 보존한 이전 이미지 ID와 백업을 사용한
개별 복구 계획으로 전환하고 운영 상태를 미복구로 표시한다.

이 절차에는 운영 배포를 자동으로 시작하는 GitHub 작업이 없다. 서버 접근 권한과
배포 승인 경계를 정한 뒤 수동 실행 워크플로로 연결할 수 있다.
