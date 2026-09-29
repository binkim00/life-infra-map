# 소셜 로그인 운영 연결

코드는 기본적으로 비활성화되어 있다. 공급자 앱 설정과 실제 인증 왕복을 확인한 뒤에만 켠다.

현재 공개 서비스 주소가 `https://life-infra-map-db.taile29cc8.ts.net`인 동안 세 공급자의 웹 로그인 리다이렉트 URI는 다음과 같다.

```
https://life-infra-map-db.taile29cc8.ts.net/spring/api/login/oauth2/code/google
https://life-infra-map-db.taile29cc8.ts.net/spring/api/login/oauth2/code/naver
https://life-infra-map-db.taile29cc8.ts.net/spring/api/login/oauth2/code/kakao
```

Google OAuth 클라이언트는 웹 애플리케이션 유형으로 만들고 승인된 리다이렉트 URI를 등록한다. Kakao는 카카오 로그인과 이메일 동의 항목을 확인한다. Naver 앱은 네이버 로그인 API를 켠다. Naver는 이메일 검증 플래그가 없어 이메일이 제공되더라도 기존 계정에 자동 연결하지 않는다. 이 주소는 공개 도메인이 바뀌면 공급자 콘솔과 서버를 함께 수정해야 한다.

2026-09-28 콘솔 확인: 세 공급자의 현재 공개 콜백이 등록됐다. Google `LifeMap`은 테스트 상태이며 `kimyb301@gmail.com`만 테스트 사용자로 추가됐다. Naver `lifemap`은 개발 중 상태다. Kakao `LifeMap`은 로그인과 이메일 필수 동의가 켜져 있다. 세 공급자 모두 서버 자격증명을 주입하지 않아 실제 로그인 왕복은 아직 검증되지 않았다. Google 클라이언트 비밀값은 사용자가 개인 보관함에 직접 저장했다.

서버의 Spring 컨테이너에 아래 환경 변수만 주입한다. 값은 이 문서나 Git에 남기지 않는다.

서버 터미널에서 `python3 /home/ubuntu/life-infra-map/app/deploy/spring-api/configure-social-env.py`를 실행하면 값을 화면에 표시하거나 쉘 기록에 남기지 않고 `deploy/spring-api/.env`에 저장한다. 사용하지 않을 공급자는 Enter로 건너뛸 수 있다. 클라이언트 ID를 입력한 공급자는 그 직후 비밀키도 입력해야 한다.

```
SOCIAL_LOGIN_ENABLED=true
SOCIAL_PUBLIC_BASE_URL=https://life-infra-map-db.taile29cc8.ts.net
SOCIAL_GOOGLE_CLIENT_ID=...
SOCIAL_GOOGLE_CLIENT_SECRET=...
SOCIAL_NAVER_CLIENT_ID=...
SOCIAL_NAVER_CLIENT_SECRET=...
SOCIAL_KAKAO_CLIENT_ID=...
SOCIAL_KAKAO_CLIENT_SECRET=...
```

각 공급자는 ID와 Secret이 모두 있을 때만 `/api/auth/social/providers`에 나타난다. 로그인은 브라우저 세션에서 공급자 인증 상태를 확인한 다음 2분짜리 일회용 표를 앱으로 돌려주고, 앱이 그 표를 액세스/갱신 토큰으로 교환한다. Google의 `email_verified`, Kakao의 `is_email_verified`와 `is_email_valid`가 참일 때만 같은 이메일의 활성 일반 계정에 자동 연결한다. Naver 응답에는 이 기준을 판정할 검증 플래그가 없어 별도 계정을 만든다. 같은 공급자 고유 ID는 이후 기존 연결 계정으로 로그인한다.

운영 확인 순서:

1. Django `accounts.0005`~`0007`을 적용하고 Spring의 DB 스키마 검증이 통과하는지 확인한다.
2. 공급자 콘솔에 위 주소를 등록하고 환경 변수를 비밀 저장 영역에 넣은 뒤 Spring을 재시작한다.
3. `/spring/api/auth/social/providers`의 노출 목록을 확인한다.
4. 웹과 설치형 앱에서 각 공급자 인증, 취소, 검증 이메일 연결, 다른 이메일 신규 계정, 만료/재사용 표 거부, 기존 일반 로그인과 로그아웃을 확인한다.
