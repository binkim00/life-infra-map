# life-infra-map frontend

React 19와 Vite로 구성된 프런트엔드입니다.

```bash
npm ci
npm run dev
```

기본 개발 서버는 `http://localhost:5173`에서 실행됩니다. 테스트는 `npm test`, 배포 빌드는 `npm run build`로 확인합니다.

## 백엔드 연결

PC가 EC2와 같은 Tailscale 네트워크에 연결된 상태에서 실행합니다.

```bash
npm run dev
```

기본 설정으로 검색·추천 요청은 Django
`http://100.71.169.91:8000/api`, 로그인·게시판·저장 장소 요청은 Spring
`http://100.71.169.91:8081/api`로 보냅니다.

다른 백엔드를 사용할 때만 `VITE_API_BASE_URL`과
`VITE_SPRING_API_BASE_URL` 환경변수로 주소를 덮어씁니다. 연결 전
`npm run check:server`로 두 API의 health 응답을 확인할 수 있습니다.
