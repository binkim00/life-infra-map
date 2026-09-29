# 공개 HTTPS 진입점

`yeogiljido.com`의 80/443 요청을 Caddy가 받아 기존 로컬 게이트웨이
`127.0.0.1:3000`으로 전달한다. Caddy의 인증서 저장소는 Docker 볼륨에
유지한다. HTTPS 리스너는 EC2 사설 주소 `172.31.32.178`에만 묶어 기존
Tailscale 전용 주소의 443 리스너와 충돌하지 않게 한다. 로컬 게이트웨이는
그대로 둔다.

## 적용 전 확인

1. EC2에 고정 공인 IPv4를 연결하고 Porkbun의 루트 `A` 레코드를 해당 IP로
   바꾼다. 기존 판매처 기본 `ALIAS`와 와일드카드 `CNAME`은 공개 접속 범위에
   맞게 정리한다. 메일 `MX`/`TXT`는 별도 검토 없이 삭제하지 않는다.
2. `yeogiljido.com`의 공개 DNS가 새 IP를 반환하는지 확인한다.
3. EC2 보안 그룹에서 TCP 80/443만 공개하고 SSH 접근 규칙은 보존한다.
4. 기존 게이트웨이의 건강 상태와 관리자 API 인증 응답을 확인한다.

## 배포·복구

서버의 `app/deploy/public-edge/`에 두 파일을 복사하고
`docker compose -f docker-compose.yml config` 및
`docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.11.4-alpine caddy validate --config /etc/caddy/Caddyfile`
검증 후 `docker compose up -d` 한다. 인증서 발급과 공개 HTTPS·HTTP 리다이렉트,
API·지도 임베드·웹 화면을 실제 외부망에서 확인한다.

문제가 있으면 `docker compose down`으로 공개 진입점만 내리고 보안 그룹의
80/443 규칙을 되돌린다. 기존 Tailscale 연결과 백엔드는 유지한다. DNS를
판매처 기본 주소로 되돌리는 것은 별도 판단이며, 구매한 도메인은 유지한다.
