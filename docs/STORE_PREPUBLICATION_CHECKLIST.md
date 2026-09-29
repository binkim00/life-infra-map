# 여기일지도 스토어 게시 전 확인 목록

2026-09-29 기준. `완료`는 적힌 범위에서만 검증됐다는 뜻이다. `확인 필요`는 코드 검색이나 이전 기록만으로 운영 결과를 단정할 수 없는 항목이다. 앱 출시 승인을 뜻하지 않는다.

## 1. 현재 판단

**Android와 iOS 모두 공개 게시 준비 전이다.** 웹 HTTPS와 API 상태, CI 검사, 테스트 Android APK의 이름·아이콘은 확인했다. 출시 앱의 공개 주소, 스토어용 빌드, 스토어 계정·정책 입력, 전체 실기기 흐름은 아직 검증되지 않았다. 웹을 앱 소개 페이지로 바꾸는 일과 CD 완전 자동화는 스토어 심사의 선행 조건이 아니다. 단, 공개 개인정보처리방침·계정 삭제 요청·고객 지원 주소는 필요하다.

## 2. 공통 출시 차단 항목 — 먼저 해결

| 상태 | 확인할 것 | 현재 근거와 완료 기준 |
| --- | --- | --- |
| 미완료 | 공개 서버 주소로 앱 빌드 | `mobile/eas.json`, `mobile/app.config.js`, 일부 모바일 코드의 기본값이 내부 `.ts.net` 주소다. 출시 설정을 `https://yeogiljido.com`으로 바꾸고 **Tailscale 없이** 로그인·지도·검색·사진·문의까지 실기기 검증한다. |
| 미완료 | 소셜 로그인 새 주소 | 공개 웹의 Google 로그인 시작은 현재 내부 `.ts.net`으로 302 이동한다. Google·Naver·Kakao 개발자 콘솔의 허용 도메인·콜백, 서버 설정, 앱 복귀를 공급자별로 왕복 검증한다. 기존 앱 사용자 전환도 확인한다. |
| 미완료 | 로그인 요청 제한 | `PublicWriteRateLimitFilter`가 프록시 주소로 이용자를 합산하는 구조다. 신뢰된 프록시에서만 실제 사용자 IP를 받고, 서로 다른 사용자·헤더 위조·직접 내부 접속 테스트를 통과한다. [보안 점검](SECURITY_REVIEW_2026-09-29.md) 참조. |
| 미확인 | 계정 삭제와 데이터 처리 | 앱에 회원가입은 있지만 현재 모바일 화면·서버 코드 검색에서 이용자용 계정 삭제 경로를 찾지 못했다. 앱 안에서 삭제를 시작할 수 있어야 하며, Google Play용 공개 웹 삭제 요청 주소도 준비한다. 게시물·제보·문의·저장·소셜 연결 등 연관 데이터의 삭제/보존 기준을 정하고 실제 삭제를 검증한다. [Google Play](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en), [Apple](https://developer.apple.com/support/offering-account-deletion-in-your-app). |
| 미확인 | 개인정보처리방침·이용약관·지원 | 저장소에서 공개 개인정보처리방침/삭제 요청 페이지를 확인하지 못했다. 실제 수집·공유·보관 정보(계정, 위치, 사진, 게시물, 검색·문의 기록 등)를 확인해 문서와 앱/스토어 입력값을 일치시킨다. 문의 가능 주소와 공개 지원 페이지를 준비한다. [Google Play](https://support.google.com/googleplay/android-developer/answer/9859455?hl=en), [Apple](https://developer.apple.com/help/app-store-connect/reference/app-information/app-privacy/). |
| 일부 완료 | 공개 게시물 운영 | 게시글·댓글 신고와 관리자 처리 화면은 있다. 게시 전 이용약관 동의, 부적절한 콘텐츠 필터, 사용자 차단/숨김 및 처리 시간·운영 절차는 별도 확인·구현이 필요하다. [Google Play UGC](https://support.google.com/googleplay/android-developer/answer/9876937?hl=en-GB), [Apple 1.2](https://developer.apple.com/app-store/review/guidelines/). |
| 미확인 | 외부 자료·지도·사진 사용 권한 | 카카오 지도/장소 정보, 수집한 사진·문구와 사용자 게시물의 표시·저장·출처 표기가 각 제공자 조건 및 스토어 설명과 맞는지 확인한다. 확인되지 않은 장소 속성을 검증된 사실처럼 표시하지 않는다. |

## 3. Android / Google Play

| 상태 | 확인할 것 | 현재 근거와 완료 기준 |
| --- | --- | --- |
| 미확인 | 개발자 계정·앱 등록 | 마지막 확인에서 계획 계정은 Play Console 가입 시작 화면이었다. 등록·결제·본인 인증·패키지 소유 여부를 콘솔에서 재확인한다. [2026-09-30부터 패키지 등록 관련 안내](https://support.google.com/googleplay/android-developer/answer/16984799?hl=en). |
| 미완료 | 출시용 AAB·서명 | 설치해 본 파일은 `com.binkim00.lifeinframap.test` APK다. 출시 패키지 `com.binkim00.lifeinframap`의 AAB, 업로드 키 보관, Play App Signing, 고유 버전 코드를 확인한다. [Play 앱 설정](https://support.google.com/googleplay/android-developer/answer/9859152?hl=en). |
| 확인 필요 | API 수준·기기 호환 | 2026-08-31부터 신규 일반 Android 앱은 target API 36 이상이 필요하다. 실제 AAB의 target SDK를 확인하고 16KB 메모리 페이지 호환성을 분석·실행 검증한다. [API 기준](https://support.google.com/googleplay/android-developer/answer/11926878?hl=ko), [16KB 안내](https://developer.android.com/guide/practices/page-sizes). |
| 확인 필요 | 테스트 트랙 | 내부 테스트를 먼저 진행한다. **2023-11-13 이후 만든 개인 개발자 계정이라면** 공개 배포 접근 신청 전에 최소 12명이 연속 14일 참여하는 비공개 테스트가 필요하다. 계정 유형·생성일을 확인한다. [Play 테스트 요건](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en-GB). |
| 미완료 | Play 정책 입력 | 앱 접근용 심사 계정/설명, 데이터 보안, 데이터 삭제, 위치·사진 권한, 광고 여부, 대상 연령, 콘텐츠 등급, 연락처·개인정보처리방침을 실제 동작과 맞춰 입력한다. 심사에는 운영 관리자 계정 대신 별도 재사용 가능한 테스트 계정을 제공한다. [Play 검토 준비](https://support.google.com/googleplay/android-developer/answer/9859455?hl=en), [로그인 정보](https://support.google.com/googleplay/android-developer/answer/15748846?hl=en-GB). |

## 4. iOS / App Store

| 상태 | 확인할 것 | 현재 근거와 완료 기준 |
| --- | --- | --- |
| 미확인 | 개발자 계정·앱 등록 | 마지막 확인에서 App Store Connect는 로그인 화면이었다. Apple Developer 멤버십, 팀, 앱 ID와 `com.binkim00.lifeinframap` 등록 여부를 확인한다. |
| 미완료 | iOS 빌드·TestFlight | IPA·iPhone 실기기·TestFlight 검증 기록이 없다. 서명/프로비저닝을 마치고 로그인, 지도, 권한 거부, 사진, 검색·문의·게시물, 로그아웃을 iPhone에서 확인한다. |
| 확인 필요 | 소셜 로그인 심사 | Google·Naver·Kakao처럼 제3자 로그인을 기본 계정에 쓴다면 Apple 4.8의 동등한 개인정보 보호 로그인 선택지를 제공해야 한다. 현재 코드에서 그 선택지를 확인하지 못했다. Apple 로그인 도입 또는 지침을 만족하는 다른 방안을 결정하고 검증한다. [Apple 4.8](https://developer.apple.com/app-store/review/guidelines/). |
| 미완료 | App Store 정보 | 앱 개인정보 문답·정책 URL·지원 URL, 연령 등급, 실제 화면 스크린샷, 심사용 계정/설명, 콘텐츠 권리와 지역을 입력한다. [Apple 필수 항목](https://developer.apple.com/help/app-store-connect/reference/app-information/required-localizable-and-editable-properties/). |

## 5. 실제 이용 흐름 합격 기준

- **첫 설치/비회원:** 앱 실행, 홈·검색·추천·저장·MY 탭, 위치 권한 거부 후 수동 지역 검색, 빈 결과·느린 네트워크·서버 오류 표시.
- **계정:** 이메일 가입·로그인, Google·Naver·Kakao 로그인, 앱 재실행 후 세션 유지, 로그아웃, 만료 토큰 갱신, 비밀번호/계정 복구, 계정 삭제. iOS는 추가 로그인 선택지 검증.
- **검색/지도:** 일반·카테고리·상황·필터 검색의 대표 지역 표본, 중복 장소 제거, 지도 중심/마커, 근거 부족·부분 일치 표기, 첫 요청 속도. `서면에서 조용한 카페`처럼 예전에 문제가 났던 사례 포함.
- **장소 상세/콘텐츠:** 카카오 상세 링크 유무에 따른 동작, 외부 링크·사진·주소 정확성, 카드 스크롤, 저장·장소 제보·문의·게시글/댓글·신고, 관리자 검토와 권한 차단.
- **기기/운영:** Android 여러 화면 크기와 버전, iPhone, 권한 허용/거부, Wi-Fi/모바일망, Tailscale 미설치 상태, 재설치/업데이트 시 데이터 유지. 공개 HTTPS·백업 복원·장애 경보·서버 용량(90% 기준)·실패 배포 복구 확인.

## 6. 스토어 설명과 게시 순서

1. 공개 주소·인증·계정 삭제·UGC 정책의 차단 항목을 해결하고, 출시 빌드로 위 이용 흐름을 검증한다.
2. 실제 기능만 설명하는 앱 이름, 아이콘, 설명, 스크린샷, 권한 설명, 고객 지원·개인정보처리방침·삭제 주소를 준비한다. 웹 첫 화면을 앱 소개로 바꾸는 것은 선택 사항이다.
3. Android AAB → Play 내부 테스트 → 해당되면 12명/14일 비공개 테스트 → 공개 배포 접근 신청·심사 순으로 간다. iOS는 계정·로그인 요건 확정 → IPA → TestFlight → App Store 심사 순으로 간다.
4. 공개 후 오류율·로그인·검색 품질·문의/신고 대응·디스크/백업을 모니터링한다. CD 완전 자동화는 출시 필수 조건은 아니지만 수동 배포의 백업·검증·복구 절차는 필요하다.
