# 출시 기반 검증 기록 (2026-09-30)

## 결정과 범위

- Android를 먼저 준비한다. iOS 출시와 Apple 로그인은 사용자 결정에 따라 보류한다.
- 계정 삭제는 공개 게시글·댓글의 작성자를 공용 탈퇴 계정으로 익명화하고,
  나머지 계정 종속 데이터를 삭제한다. 백업은 최대 30일 이내 만료시킨다.
- 공개 운영 주체는 ‘여기일지도 개발진’, 지원 이메일은 `kimyb301@gmail.com`이다.

## 코드로 확인한 것

| 항목 | 근거 | 범위 |
| --- | --- | --- |
| 앱 공개 주소 | `mobile/eas.json`의 preview/production 3개 주소, `app.config.js`의 출시 주소 검사 | 빌드 설정만 확인. 설치본 미검증 |
| Android 식별자 | Expo 설정 평가에서 `com.binkim00.lifeinframap`, 버전 `1.0.2` | 실제 AAB/서명/버전 코드 미검증 |
| 요청 제한 | Spring 필터 3개 단위 테스트 통과: 이용자 분리, 직접 접속 위조, 신뢰 설정 누락. 공개 3001 포트와 사설 3000 포트 분리, Compose 설정 검사 통과 | 실제 Nginx 구동·컨테이너 IP·외부망 미검증. 이 PC에는 Docker 데몬이 없음 |
| 계정 삭제 | Django 4개 테스트 통과: 계정·문의·발신 알림 삭제, 게시글·댓글 익명화, 확인 문구·관리자 차단, 게시글 파일 삭제 | 운영 실제 사용자 데이터 삭제는 미실시 |
| 앱 화면 | 모바일 TypeScript 검사 및 기존 요청 재시도 검사 6개 통과 | 실기기 화면·접근성 미검증 |
| 공개 문서 | `/privacy.html`, `/support.html`, `/delete-account.html` 정적 파일과 앱 설정 링크 | 운영 웹 배포·실제 접속 미검증 |

## OAuth 콘솔 변경 및 재확인

- Google LifeMap 웹 클라이언트: 새 `https://yeogiljido.com/spring/api/login/oauth2/code/google`
  콜백을 추가했고 기존 `.ts.net` 콜백도 유지한 상태를 다시 열어 확인했다.
- Naver `lifemap`: 서비스 URL을 공개 주소로 바꾸고 새 `/spring/api/login/oauth2/code/naver`
  콜백을 추가했다. 기존 `.ts.net` 콜백은 유지했다. 다시 열어 저장을 확인했다.
  앱은 여전히 개발 중이며 등록 멤버만 로그인 가능하다는 콘솔 안내가 있다.
- Kakao LifeMap REST 키: 새 `/spring/api/login/oauth2/code/kakao` 콜백을 추가했고
  기존 `.ts.net` 및 개발 주소를 유지했다. 재열람으로 저장을 확인했다.
- Kakao JavaScript 키: `https://yeogiljido.com`을 JS SDK 허용 도메인에 추가하고
  기존 도메인을 유지했다. 재열람으로 저장을 확인했다.
- 운영 서버의 `SOCIAL_PUBLIC_BASE_URL` 반영과 공급자별 웹·Android 왕복은
  아직 완료되지 않았다. 인증 비밀값은 이 문서에 기록하지 않는다.

## 운영 및 스토어 게이트

1. 운영의 최신 백업 업로드와 별도 복원, 디스크 여유, 선별 파일 원본 보관,
   프록시의 정확한 주소를 확인한다. 설정/이미지 변경은 기존 파일을 보존하며
   롤백 경로를 마련한다.
2. 공개 OAuth 콜백과 Kakao JavaScript 허용 도메인은 등록했다. 공급자별
   테스트 계정의 승인 범위 및 앱 복귀를 확인한다.
3. 운영 배포 후 공개 HTTPS에서 개인정보처리방침·지원·삭제 요청 경로,
   두 접속자 로그인 한도, 위조 헤더, 직접 내부 접속을 확인한다. 실제 계정
   삭제 시험은 별도 일회용 계정과 데이터 정리 계획으로 수행한다.
4. Android 출시 패키지 AAB를 생성하고 서명·고유 버전 코드·target SDK·
   16KB 페이지 호환성을 산출물에서 확인한다. 공개 주소 설치본으로 기능별
   정상·실패·권한 거부를 실기기에서 확인한다.
5. Google Play 개발자 계정·패키지 소유, 내부 테스트, 데이터 보안·접근
   정보·정책 URL·콘텐츠 정보는 실제 동작에 맞춰 작성한다. 결제와 제출은
   별도 결정한다.

[Google Play 계정 삭제 요구사항](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en),
[Google Play 대상 API 기준](https://support.google.com/googleplay/android-developer/answer/11926878?hl=ko),
[Expo SDK 57 대상 API 표](https://docs.expo.dev/versions/latest/),
[개인정보위 처리방침 작성지침](https://www.privacy.go.kr/front/bbs/bbsView.do?bbsNo=BBSMSTR_000000000049&bbscttNo=20806)을
참고했다. SDK 57의 문서상 target SDK는 36이지만 실제 출시 AAB에서 확인해야 한다.
