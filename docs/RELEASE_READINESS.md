# 여기일지도 출시 준비 상태 (2026-09-29)

## 확인된 상태

| 항목 | 현재 상태 | 다음 조건 |
| --- | --- | --- |
| 자동 검사(CI) | GitHub Actions [실행 #1](https://github.com/binkim00/life-infra-map/actions/runs/36537940292)에서 Django·Spring·웹·앱 코드 네 작업 성공 | 기본 브랜치 병합 전 검사 필수 규칙은 별도 설정 |
| 자동 배포(CD) | 미구축. 현재 운영 반영은 선별 백업·배포·검증 방식 | 배포 대상·승인 단계·복구 절차 확정 후 별도 수동 실행 워크플로부터 시작 |
| Android 앱 이름·아이콘 | `여기일지도` 설정, `여기일지도 (테스트)` APK 실기기 설치·실행 및 패키지 이름/아이콘 리소스 확인 | 출시용 AAB와 서명 키, Play Console 등록 및 스토어 화면 검증 |
| Google Play | 현재 Chrome의 `kimyb301@gmail.com`은 Play Console 개발자 계정 만들기 화면으로 이동 | 사용할 소유 계정과 개발자 등록·결제·인증 결정 |
| App Store Connect | 현재 Chrome에서 Apple 계정 로그인 화면 | Apple Developer 팀/멤버십 및 기존 앱 등록 여부 확인 |
| iOS | Expo 설정에 `com.binkim00.lifeinframap` 식별자 있음. IPA 빌드·iPhone 실기기·TestFlight 검증 없음 | Apple 계정과 빌드 환경 확보 후 실기기 검증 |
| 공개 서버 연결 | `mobile/eas.json`의 preview/production 주소가 Tailscale `.ts.net` 주소 | 일반 사용자가 접근할 공개 HTTPS 주소와 OAuth·지도 허용 도메인 검증 |

## 공식 주소 후보

- 사용자는 서비스 이름을 로마자로 쓰는 주소를 선호한다. `yeogiiljido.com`은 2026-09-29 판매처 검색에서 등록 가능으로 표시됐고, 당시 표시된 첫해·갱신 가격은 각각 연 **US$11.08**이었다. 등록 가능 여부와 결제 가격은 구매 시점에 다시 확인해야 한다. 아직 구매하지 않았다. [판매처의 .com 가격](https://porkbun.com/products/domains)
- 현재 AWS 계정은 Route 53 Domains의 등록 가능 여부·가격 조회에서 `Free Tier accounts are not supported for this service`를 반환했다. 해당 계정으로 도메인을 등록한다는 전제를 두지 않는다. 외부 등록업체의 DNS 관리 기능을 사용하면 Route 53 호스팅 영역을 새로 만들 필요는 없다.
- 운영 EC2의 현재 주소는 자동 할당 IPv4다. 중지·시작 뒤 변경될 수 있으므로 도메인을 연결하기 전에 고정 주소(Elastic IP 등)를 정하고, MobaXterm 접속 정보도 새 주소로 갱신해야 한다. AWS는 현재 자동 할당 IPv4와 사용 중 Elastic IP에 동일한 시간당 공인 IPv4 요금을 안내한다. [EC2 주소 지속성](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-stop-start-works.html) · [공인 IPv4 요금](https://aws.amazon.com/vpc/pricing/)
- 현재 게이트웨이는 서버 내부 `127.0.0.1:3000`에서만 수신한다. 공개 도메인을 확정한 뒤 HTTPS 종단을 앞에 두고 `/django/api/`, `/spring/api/`, `/kakao-map-embed.html`, 웹 화면이 정상 동작하는지 점검한다. 그 후 모바일 API 주소, 소셜 로그인 콜백, Kakao 허용 도메인을 함께 변경한다. 공개 전에 관리자 접근 범위와 API 권한도 다시 검증한다.

## 권장 진행 순서

1. **공개 HTTPS 연결:** Django·Spring·카카오 지도 임베드의 안정적인 공개 도메인을 정하고, 인증·지도·검색·문의의 실제 휴대폰 연결을 점검한다. 현재 `eas.json` 값을 그대로 출시용으로 사용하지 않는다.
2. **Android 출시 준비:** Play 개발자 계정을 정하고 앱을 등록한다. 출시용 패키지 `com.binkim00.lifeinframap`에 맞는 서명·AAB를 만들고 내부 테스트 트랙에서 로그인, 지도, 검색, 문의, 관리자 권한을 검증한다. 지금 설치한 `.test` APK는 스토어 업로드물이 아니다.
3. **iOS 빌드:** Windows PC에서는 Android 로컬 빌드를 계속 사용한다. iOS는 우선 Expo EAS의 macOS 빌드 환경을 사용해 첫 IPA와 TestFlight 검증을 진행하는 것이 현실적이다. 빌드 횟수·비용이 부담되면 macOS/Xcode 로컬 빌드 환경을 확보한 뒤 옮긴다. EAS Submit은 Windows에서도 실행할 수 있다. [Expo 로컬 빌드](https://docs.expo.dev/build-reference/local-builds/) · [iOS 제출](https://docs.expo.dev/submit/ios/)
4. **자동 배포:** CI가 안정적으로 유지되고 공개 연결 및 출시 경로가 정해지면, 처음에는 명시적으로 눌러 실행하는 배포 흐름을 만든다. 배포 전 백업, 배포 후 상태·핵심 API 검사, 실패 시 복구를 기록한다. 자동으로 모든 push를 운영에 배포하는 방식은 운영 검증이 쌓인 뒤 결정한다.
5. **스토어 제출:** 개인정보 처리방침·문의 경로·스토어 설명·스크린샷·데이터 수집/권한 내용을 실제 앱과 맞춰 작성한다. Android는 Play 내부 테스트, iOS는 TestFlight를 거친 뒤 심사 제출 여부를 결정한다. [Google Play 게시 절차](https://support.google.com/googleplay/android-developer/answer/9859751?hl=ko) · [App Store Connect 절차](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-workflow/)

## 출시 판단에 남은 제품 검증

- 근거 자동 승인과 부족한 지역·조건 근거 수집은 운영 평가가 더 필요하다. 검색이 확인되지 않은 속성을 사실처럼 보여주지 않는 현재 기준을 유지한다.
- 검색 평가에서 근거 부족으로 보류된 사례, 카카오 개별 장소 링크가 없는 사례, 실제 기기에서의 소셜 재로그인과 화면 동작을 출시 전에 재확인한다.
