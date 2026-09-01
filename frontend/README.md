# life-infra-map frontend

React 19와 Vite로 구성된 프런트엔드입니다.

```bash
npm ci
npm run dev
```

기본 개발 서버는 `http://localhost:5173`에서 실행됩니다. 테스트는 `npm test`, 배포 빌드는 `npm run build`로 확인합니다.

## EC2 백엔드 연결

PC가 EC2와 같은 Tailscale 네트워크에 연결된 상태에서 실행합니다.

```bash
npm run dev:server
```

이 모드는 `.env.server`를 읽어 검색·추천 요청은 Django
`http://100.71.169.91:8000/api`, 로그인·게시판·저장 장소 요청은 Spring
`http://100.71.169.91:8081/api`로 보냅니다. 기본 `npm run dev`는 기존처럼
로컬 백엔드에 연결됩니다.

서버 연결 설정으로 빌드할 때는 `npm run build:server`를 사용합니다.
연결 전 `npm run check:server`로 두 API의 health 응답을 확인할 수 있습니다.
