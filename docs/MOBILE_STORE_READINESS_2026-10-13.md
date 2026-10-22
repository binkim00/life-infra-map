# 모바일·스토어 출시 준비 점검 — 2026-10-13

## 2026-10-14 정식 수정 AAB 검증 완료 — 아직 Play에 업로드하지 않음

최신 고정master c58d885c/146파일의EASproduction code6 빌드 a056e467-0a75-4d37-9436-75e43f097768 성공. 사용자 추가 직접 승인 후 기존등록업로드키로서명만정정한최종로컬AAB `artifacts/local-builds/lifemap-production-code6-master-c58d885c-20261014.aab`·76,043,494bytes·SHA `35c393f47f7adf8d435b3933da5cb202f5eb366f188329bc4fb18c0145981ae4`. 정식package/1.0.2/code6/target36/min24·공개3주소·jarsigner내용검증·현재Play업로드cert4df89b32...일치. 서명외1406entry hash보존·임시키삭제·기존키/EAS·Play설정불변.

16KB ELF46개/LOAD140/최소16384/미달0·BundleConfig16K·파생검사용APK native92 ZIP정렬/zipalign exit0 통과. Free3/30/현재비용0·새키/유료빌드/결제/기기설치·데이터변경없음. 원격EAS원본 SHA2e6ee185.../서명3e2147ad...와 최종로컬후보35c393f4.../서명4df89b32...를구분한다. 상세[최종보고](MOBILE_FULL_QA_2026-10-13.md).

Play 현재code5/참여0·12명14일·프로덕션비활성 및 테스터 준비 문서는 그대로다. 새code6 Play업로드/게시/제출/테스터초대는 이번범위에서 실행하지 않았다. 정식16KB물리실행·OAuth완료·공개업로드/iOS도 별도범위. 다음한가지행동은 별도요청/승인시최종로컬AAB의비공개테스트후보업로드다.

## 2026-10-14 새 정식 AAB 요청 — 전송 준비 완료

최신 원격 master c58d885c의 독립 mobile/shared146파일 source archive 검증 완료(4,990,074bytes, SHA f174328f14b74c76b4a2b13aa4110754b32829eb2a6a9a617a8331444c91fff6). EAS 계정 yeongbinkim/project life-infra-map/c3a1fd87-d9e4-4b54-8702-c30fda27b86e, Free BUILDS2/30·현재비용0, remote code5·다음production code6예정, 정식 package/공개3endpoint를 확인했다. 필수entry/shared/lock/config 포함·Git blob일치146개·secret/환경파일/DB/runtime/APK/native/기기자료 제외. 공유 파일/데이터 보존.

소스 전송 목적지 Expo EAS에 대한 직접 승인 부족으로 자동 심사가 build 실행을 거절했다. 새 AAB는 아직 없으며 기존 성공code5/테스트APK를 새산출물로 대체하지 않는다. 현재 Play 업로드 인증서4df89b32...의 부모 직접조회와 기존 AAB signer 일치는 확인자료이며 새수정판 signer 대조는 빌드 후다. [정확한 전송 범위](MOBILE_FULL_QA_2026-10-13.md)를 확정했으므로 다음 행동은 Expo에146파일 전송·무료production/code6 기존키빌드의 명시 승인 요청이다. 제출/새키/결제는 포함하지 않는다.

## 2026-10-14 실기기 후속과 AAB 서명 읽기

기존 code5 AAB는 jarsigner exit0·jar verified·unsigned entries 경고없음, signer cert SHA256 `4df89b32c659cb77e964a57d1e646bc3c01027fedd5d931fddaa80f914301242`로 내용 서명을 확인했다. 공개 CA chain/self-signed 경고는 내용 서명 오류와 구분한다. Play 업로드/앱서명 인증서 대조는 미완료다. 현재 native는 `.test / code4 / debug signing`으로 정식 AAB 제출용이 아니다. 출시 후보는 기존 업로드키 접근과 production native/package·remote version 반영 경로를 격리 context에서 확정해야 하며 새 키·유료 빌드·제출은 하지 않았다.

부모가 물리 Android 연결을 확인했으나 이 채팅 ADB 승인실행 최초/재시도는 deadline 시간 초과, sandbox 조회는 기기 접근0으로 실기기 검증 미완료다. 실제 기기 부재로 판정하지 않는다. 새 Play 탭도 deadline으로 생성되지 않아 앞선10/14 직접 읽기 조회를 재사용한다. OAuth는 공급자 진입까지만 유지. 종료보고 전송은 자동 심사가 목적지 승인/내부정보 문제로 거절해 실행하지 않았다. [후속 상세·잔여 절차](MOBILE_FULL_QA_2026-10-13.md)에 기록했다.

## 2026-10-14 최종 현황 — 아래 최초 점검 표보다 최신

모바일 수정2건은 종료됐고 제품 소스3개/검사2개의 최종 hash를 [QA 최종 인계](MOBILE_FULL_QA_2026-10-13.md)에 고정했다. 수정 테스트 APK `.test / 1.0.2 / code4`, SHA `2e9ebd7386ea531fa3da32031416c824474b43b019802568096f414bd0414bf3`는 현재 파일 및 빌드 소스128개와 일치한다. 10/13의5검사·타입·린트·에뮬레이터 데이터 유지 설치·16KB 실행 결과를 재사용했으며 빌드/QA를 반복하지 않았다. QA 데이터 정리 완료도 유지한다.

10/14 Play 대시보드 읽기 조회: 비공개 테스트 버전 게시 완료, 참여 선택0명, 프로덕션 비활성·신청 버튼 비활성. 이는 과거 code5 게시 사실과 별개인 최신 프로덕션 접근 상태다. 현재 연결 기기0으로 물리 GPS/실기기·스토어 설치본 확인은 없다. Google/Naver/Kakao는 사용자 합의대로 공급자 화면 진입까지만 완료했다.

과거 성공 출시 code5 AAB의 현재 보존 hash `53eea938a2d25f4c5eec0e98716d9fcda732b0489777d42e96ea45266129da2c`는 이전 기록과 동일하다. 과거 code4 EAS 실패가 최신 code5 실패라는 뜻은 아니며, 이 AAB가 이번 수정2건을 포함하지도 않는다. 테스트 APK 서명·16KB 실행은 통과했으나 AAB 유효 서명/Play 업로드키·앱 서명키 대조와 수정 코드 출시 AAB·스토어 설치본 검증은 잔여다. iOS 계정/IPA/TestFlight 증거도 없다. 아래 기존 표는 최초 점검 시점의 역사이며 현 상태는 이 절과 QA 보고로 판단한다.

다음 한 가지 행동: Git 담당이 고정된5파일과 앞선 모바일 통합 변경을 보존한 후보를 준비한다. 후속 실기기/출시 검증은 사용자 기기 또는 별도 계정·산출물 접근이 필요하며 현재 범위에서 계정 삭제/공개 제출/배포/스토어 제출은 하지 않는다.

## 판단

Android는 **등록·내부/비공개 테스트 게시 완료, 프로덕션 출시 미완료**다. 현재 비공개 테스트 참여 선택 0명이며 프로덕션 신청은 비활성이다. iOS는 실제 계정·IPA·TestFlight 증거가 없다. 최신 로컬 코드, 기존 테스트 APK, Play 코드 5는 서로 다른 검증 대상이다.

담당 범위: mobile과 앱/스토어 문서. 운영 서비스·계정 정책·공유 데이터·마이그레이션·배포·스토어 제출·원격 병합을 변경하지 않았다. 다른 채팅이나 하위 에이전트에 메시지를 보내지 않았다. CPU 후속 기록의 운영 revision/경보 OK는 모바일 빌드·기기 성공 증거가 아니다.

## 현재 Git와 빌드 연결

- 현재 checkout: `codex/disk-maintenance`, HEAD `6f1f8323cc87e3def055905a69e44c3af8322221`. 기존 mobile/frontend/backend/shared의 tracked/untracked 변경을 보존했다. checkout 전환/reset/clean/stash/커밋은 하지 않았다.
- 별도 release-foundation worktree HEAD: `5550de6532ae014ec6cbf923ebc0659097e1a2c2`. service-flow-verification HEAD: `7d5b9a016ca362e07bc344c76fae237e86e0fe9c`.
- **EAS 현재 직접 조회**: 최신 성공 Android production 빌드 `9dfc1dc7-12f8-483c-8907-8f0e5cd482da`, `1.0.2 / code 5`, 소스 기록 `e16d995f5c8bec519809940ba7da8c3bf340c271`, 생성 `2026-10-06T05:25:31.612Z` = 10월 6일 14:25:31 KST. 웹 빌드 페이지는 commit에 `*`도 표시하므로 SHA만으로 업로드 소스가 clean checkout과 완전히 동일하다고 단정하지 않는다. EAS 성공은 5550de65 이후 문서 수정까지 포함한 빌드라는 뜻이 아니다.
- code 4 빌드는 `f4648ebf...`, ERRORED. code 3은 `fbb91ee9...`, 10월 2일 성공. 따라서 초기 AAB 실패/쿼터 소진 문서는 최신 산출물 상태가 아니다. 최신 5건 조회에 iOS는 없지만 프로젝트 전체 iOS 이력이 없다는 증명은 아니다.
- EAS 출처: https://expo.dev/accounts/yeongbinkim/projects/life-infra-map/builds/9dfc1dc7-12f8-483c-8907-8f0e5cd482da
- 로컬 보존 AAB: `C:/Users/SSAFY/.codex/worktrees/6180/life-infra-map/artifacts/lifemap-production-code5.aab`, 76,016,567 bytes, SHA256 `53EEA938A2D25F4C5EEC0E98716D9FCDA732B0489777D42E96EA45266129DA2C`. 파일명/기존 기록과 EAS/Play code5는 일치하나 이번에 EAS 원본을 다시 내려받아 바이트 동일성을 대조하지는 않았다.
- 현재 checkout의 기존 APK: `mobile/android/app/build/outputs/apk/release/app-release.apk`, SHA256 `6B0C602068BBA2F3E2151376CD6FBA046D91C3B474EFAA2BD2F33822693B7172`, `.test / 1.0.2 / code4 / target36 / min24 / 여기일지도 (테스트)`를 aapt로 확인. 생성 SHA·빌드 날짜는 확정하지 못했다. 최신 로컬 변경이 포함됐다고 해석하지 않는다.
- 10월 2일 service-flow 최종 기록의 APK: `lifemap-test-qa-20261002-complete.apk`, SHA256 `D1761E7CD268D9365A811C5B73DF498F40FA897AB63ABEBCAFA2BFA3A1748202`, `.test / 1.0.2 / code4`, 당시 양 기기 설치 해시 일치. **과거 문서 증거**이며 이번 설치본 재조회는 아니다. 문서 앞쪽 완료 보충이 아래 오래된 미완료 설명보다 최신이다. 당시 사용자 소셜 로그인 성공 보고도 현 code5 왕복 재시험으로 승격하지 않는다.

## 증거별 체크리스트

| 항목 | 코드/자동 검사 | 빌드 산출물 | 실기기 | 현재 스토어 콘솔 |
|---|---|---|---|---|
| 공개 API/지도 주소 | preview/production 3개 yeogiljido.com 주소 및 정확 일치 guard 복원·검사 통과 | 보존 AAB JS에 공개 3개 endpoint 문자열 모두 존재. 문자열 존재는 실제 모든 요청의 경로 증명이 아님 | 미확인 | code5 제공 중 |
| 앱 이름·아이콘 | app.json 여기일지도·동일 icon 경로·adaptive 배경 #0F857A | 테스트 APK label/icon 리소스 참조 확인. 출시 AAB 아이콘 픽셀 동일성 미확인 | 최신 런처 미확인 | 여기일지도·아이콘 표시 |
| package/버전 | production `com.binkim00.lifeinframap`, preview `.test`, 1.0.2. EAS remote version 관리 | 테스트 APK code4. AAB code5는 Play 직접 확인 | 설치 SHA 미확인 | 출시 패키지 등록·code5 활성, code3 비활성 |
| 서명 | .easignore가 native/debug signing 파일 제외 | AAB META-INF RSA 블록 존재. 유효 서명·인증서 fingerprint·Play 업로드키 대조는 미완료 | 기존 데이터 유지 업데이트 가능 여부 미확인 | 앱 무결성 인증서 별도 확인 필요 |
| target SDK | SDK57 설정 | 테스트 APK target36 | OS 호환 미확인 | code5 target36·API24+ |
| 16KB | SDK 버전만으로 합격 판단 안 함 | 보존 AAB 64bit ELF PT_LOAD 140개, 정렬 최소16384, 미달0 | 16KB 실행 미확인 | code5 ‘16KB 지원’ 표시 |
| 키보드/뒤로/history | 우선순위 helper·상세 WebView canGoBack 확인, UX 자동 검사 | 최신 로컬과 code5 동일성 미확인 | 전 항목 미확인 | 해당 없음 |
| 지도/카드·조건·새 대화·늦은 응답·오류 | canonical 조건·generation guard 및 상태 유지 자동 검사 통과 | 최신 통합 앱 미생성 | 미확인 | 해당 없음 |
| 위치 거부/복구 | 거부 null·수동 지역, GPS4초 제한 코드. 설정 복구 UI 별도 미확인 | 해당 OS 동작 미확인 | 미확인 | 위치 선언 상세 미확인 |
| OAuth3종·세션·계정 전환 | openAuthSessionAsync·인증 context 존재 | 공개 OAuth 실행 증거 없음 | 과거 .test 사용자 성공 보고만 있음 | 앱 접근 정보 상세 대조 미완료 |
| 사진·저장/MY | 사진 URI 객체3곳 File 복원, 타입/린트 통과. 저장 식별자 결함은 아래 참조 | 이번 수정 빌드 없음 | 10/2 photo 성공은 과거 증거 | 해당 없음 |
| 계정 삭제/정책/지원 | release worktree에 화면/링크 있음, 현재 checkout은 반영 누락 | code5의 기능 직접 실행 미확인 | 삭제 실행 안 함 | 입력된 URL·삭제 경로 대조 미완료 |
| UGC·접근·스크린샷 | 공개 제출하지 않음 | 해당 없음 | 신고/차단/운영 왕복 최신 미확인 | 등록·게시 사실만 확인, 선언/이미지 상세는 아래 절차 |
| iOS | bundleIdentifier만 구성됨 | IPA/서명 증거 없음 | 없음 | Apple 계정/TestFlight 미확인 |

## 발견 결함·이번 수정·검증

1. 현재 checkout의 EAS preview/production이 Tailscale 주소, production guard가 임의 HTTPS까지 허용했다. release-foundation의 `mobile/eas.json`, `app.config.js`만 로컬 복원했다. 3개 공개 endpoint 일치와 다른 HTTPS 거부 검사를 통과했다. 운영/EAS 환경 설정은 바꾸지 않았다.
2. release-foundation의 `mobile/metro.config.js`가 현재 checkout에 없어 외부 shared helper bundling 설정이 누락됐다. 해당 설정만 복원. 실제 새 AAB bundle 검증은 남았다.
3. 가입·MY 프로필·게시글 사진의 legacy URI-object FormData 첨부가 10/2 검증된 File 방식보다 오래됐다. 기존 화면 변경을 유지하면서 3곳만 `expo-file-system File`로 복원했다. 공개 업로드를 하지 않았으며 타입 검사는 기기 사진 성공의 대체 증거가 아니다.
4. **남은 코드 결함:** recommend 저장 payload가 외부 숫자 ID를 DB placeId로 해석할 수 있고 `source=local_db` 변환 helper가 없다. explore도 `source=db`를 그대로 전송한다. service-flow의 `saved-place-payload.ts` 수정이 현재 checkout에 반영되지 않았다. 공유 Git 통합 담당과 범위가 겹치므로 무관한 파일 전체를 덮어쓰지 않았다. 최신 통합 전 해당 수정만 보존/리뷰 필요.
5. **남은 반영 누락:** release-foundation의 앱 계정 삭제 화면·설정 링크, service-flow의 초안 복구 등 현재 checkout 미포함 파일이 있다. 이 checkout으로 새 빌드를 바로 출시하면 기존 검증 기능이 퇴행할 수 있다.

이번 검사: `npm test` 6/6, `npm run test:ux` 9/9, `npx tsc --noEmit` exit0, `npm run lint` exit0. UX 첫 실행은 sandbox 임시 파일 rename EPERM으로 테스트0건이었고 승인된 동일 검사 재실행에서 통과. File/설정 수정 후 타입·린트 재검사 통과. Expo57 versioned 문서를 읽은 뒤 수정했다. 실제 새 APK/AAB 빌드는 실행하지 않았다.

## Play 직접 확인

- 앱 목록: 출시 package로 앱1개, 비공개 테스트 상태. 앱 사용 권한과 등록은 확인했으나 외부 Android package registry 소유 인증서를 별도로 대조하지 않았다.
- 대시보드: 비공개 테스트 게시 완료, 참여 선택 **0명**, 프로덕션 비활성·신청 버튼 비활성. 설치 사용자 수와 opted-in tester 수는 다른 지표다.
- 최신 버전: Alpha code5 ‘Google Play에서 테스터에게 제공’, 내부 테스트 code5 ‘내부 테스터에게 제공됨’. 마지막 게시일10월7일. 화면마다 표시 시간이 달라 게시 상태·날짜만 확정하며 하나의 배포 시각으로 합치지 않았다.
- bundle explorer: code5 1.0.2, target36, 16KB 지원. 이는 기기16KB 실행 합격은 아니다.
- 앱 콘텐츠 직접 조회: 주의 필요는 ‘모두 확인했습니다’, 조치됨에 데이터 보안·로그인 세부정보·개인정보처리방침·콘텐츠 등급·타겟층·광고 등 선언이 있고 최종 수정10월6일이다. 이는 입력 완료 상태이며 실제 수집/정책/검토자 접근과의 정확성 대조는 미완료다. 스토어 입력 상세·인증서 대조는 확정하지 못했다. 다음 조회는 읽기 전용으로 수행하고 저장/검토 요청/출시 버튼을 누르지 않는다.

## 미확인 항목의 정확한 확인 절차

### 산출물과 설치본

EAS build ID의 AAB를 확보해 위 SHA256과 대조 → Play bundle explorer 다운로드 원본과 대조 → 앱 무결성에서 업로드/앱 서명 인증서 SHA256을 구분 → AAB 서명 검증 및 인증서 비교 → 16KB arm64 기기/에뮬레이터에서 `getconf PAGE_SIZE=16384` 확인 후 Play 설치본 실행. 앱 서명은 업로드키와 다를 수 있다. 배포 ZIP alignment와 16KB 런타임 모두 확인한다. Windows apksigner 이번 실행은 최종 검증 결과를 얻지 못했으므로 합격 처리하지 않았다.

ADB는 제한 실행 첫 시도 실패, 권한을 확보한 `adb devices` 재조회는 성공했지만 목록이 비었다. **기기가 없으므로 현재 설치본 SHA/날짜·실기기 QA 없음**. 새 기기가 연결되면 package versionName/versionCode와 설치 base APK hash, OS/WebView/page size만 기록하며 serial·계정·정확한 위치는 문서에 남기지 않는다. 앱 삭제/데이터 초기화 없이 기존 설치본이 어떤 build인지 먼저 식별한다.

### 사용자 최소 재현표 — 각 행에 build/code·OS·결과만 기록

| 흐름 | 최소 절차와 기대 결과 |
|---|---|
| 키보드·back | 검색 입력 중 키보드 열기 → 하드웨어 back으로 키보드만 닫힘 → 카드 상세 열기 → WebView 내 링크 이동 → 소프트/하드웨어 back 각각 웹 이전 페이지 → 상세 닫힘 → 패널 단계 접힘 → 이전 화면/홈. 루트 종료 안내 확인하고 종료 취소. 검색 조건/결과는 보존 |
| 지도·카드 | 결과2개 이상 검색 → 카드 선택 시 동일 provider/id 마커 선택 → 다른 마커 선택 시 같은 카드/상세. peek/expanded/collapsed에서 하단 메뉴·터치 영역·선택 유지 |
| 조건·새 대화 | ‘서면 카페’ → ‘콘센트 필수’ → 조건 추가/제거·반경 변경 → 서버 조건과 chip 비교 → 응답 대기 중 새 대화 → 이전 응답이 새 화면에 들어오지 않음. 새 대화 중복 탭도 session 중복 없음 |
| 재시도 | 검색 결과 상태에서 기기 네트워크만 잠시 끄고 후속 검색 → 오류 뒤 검색문·조건·결과 유지 → 원래 네트워크 복원 → 같은 조건 재시도. POST는 자동 재전송하지 않음. 서버500/지연은 운영 설정 변경 없이 로컬 제어 환경에서 검증 |
| 위치 | 앱 위치 권한 거부 → 수동 지역 검색 가능·무한 대기 없음 → 기기 설정에서 사용자가 허용 → 앱 복귀·위치 재시도 → 현재 위치 반영. 종료 시 이전 권한 상태는 사용자 의도에 따라 복원 |
| OAuth·전환 | Google/Naver/Kakao 각각 동의→앱 복귀→MY 확인→앱 종료/재실행→세션 확인→로그아웃. 별도 두 QA 계정 전환 때 이전 저장/MY/알림 응답이 새 계정에 섞이지 않음. 실제 토큰/계정 정보는 기록 금지 |
| 사진 | 자체 테스트 이미지 선택→미리보기→뒤로→초안 보존. 공개 제보/게시글 제출은 하지 않음. 업로드 성공은 승인된 격리 QA 대상에서만 확인. 현재 요청의 공개 제출 금지 범위에서는 미확인 유지 |
| 저장/MY | 읽기는 기존 QA 장소 상세·MY 목록 일치 확인. 저장/취소 왕복은 승인된 격리 QA 대상에서만 DB 후보/외부 숫자 ID를 각각 검사. 공유 데이터 변경이 필요한 운영 저장 시험은 별도 승인 |

### 콘솔·정책·iOS

- Play 모니터링 및 개선→정책 및 프로그램→앱 콘텐츠에서 개인정보처리방침, 데이터 보안, 앱 접근, 대상 연령·콘텐츠 등급의 완료/미완료를 조회한다. 상세 데이터 수집 유형은 실제 위치·계정·사진·제보·SDK와 대조한다. 검토자 로그인 정보는 출력/저장하지 않는다.
- 정책/지원/삭제 요청 입력값을 실제 `https://yeogiljido.com/privacy.html`, `/support.html`, `/account-deletion.html`과 대조하고 비회원 GET 접근·앱명 표시·삭제 요청 경로 발견 가능성을 확인한다. 이번 실제 URL HTTP/내용 조회는 하지 않았다. UGC 신고·차단·연락·검토 운영을 최신 앱/정책과 맞춘다.
- 사용자 늘리기→스토어 등록정보에서 이름/아이콘512/feature graphic1024×500/전화 스크린샷의 실제 업로드 및 최종 설치본과의 일치를 조회한다. 파일 존재만으로 콘솔 등록 완료를 선언하지 않는다.
- Apple Developer/App Store Connect의 팀·bundle 소유·앱 등록·서명·IPA·TestFlight build/code·기기 설치를 따로 확인한다. 새 결제/빌드/업로드/제출은 하지 않는다. 소셜3종이 기본 로그인인 현재 앱은 Apple4.8 예외/동등 로그인 충족을 검토하고 필요한 경우 제품 결정으로 남긴다. 계정 삭제·UGC도 실제 구현을 확인한다.

## 최신 공식 기준

- 일반 Android 신규/업데이트 target36 기준은 [Play API 요구사항](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en-EN)에서 확인. code5 target36은 콘솔 직접 증거.
- 16KB는 [Android 공식 가이드](https://developer.android.com/guide/practices/page-sizes) 기준으로 ELF·ZIP·실제 실행을 구분한다. 특정 앱의 유예 여부는 콘솔에서 별도 확인한다.
- 해당 신규 개인 계정은 [12명/14일 연속 참여 조건](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en)과 현재 대시보드가 일치. 현재0명으로 기간 충족을 주장할 수 없다.
- 계정 삭제 외부 경로는 [Play 삭제 요구사항](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en-EN)과 실제 앱/정책을 대조한다.
- iOS 로그인4.8·계정삭제5.1.1·UGC1.2는 [Apple 심사 기준](https://developer.apple.com/app-store/review/guidelines/) 참조. 예외 적용은 제품별 판단 필요.
- 개발은 [Expo57 공식 문서](https://docs.expo.dev/versions/v57.0.0/) 기준. SDK57/target36 표는 개별 산출물 검증의 대체가 아니다.

## 남은 출시 차단과 다음 한 가지 행동

차단: 비공개 테스터0명/14일 조건 미충족; mobile 수정이 여러 worktree·미커밋 상태로 분산되어 저장식별자/삭제/초안 기능 누락; 최신 통합 설치본의 실기기/OAuth/사진/저장/16KB 검증 없음; 서명 인증서·콘솔 선언/이미지 상세 대조 미완료; iOS 계정/빌드/동등 로그인 검토 없음.

**다음 한 가지 행동:** 공유 Git 통합 담당이 모바일 세 소스(현재 checkout, release-foundation, service-flow-verification)의 변경을 보존해 리뷰 가능한 통합 후보로 정리한다. 그 후보가 확정되기 전 이 checkout을 바로 스토어 빌드/제출하지 않는다.

## 10월 13일 후속 — 모바일 통합 후보

사용자 요청으로 세 소스의 모바일 로컬 통합 후보를 적용·리뷰했다. 위 저장식별자·계정삭제·초안복구의 checkout 누락은 해소됐으며 현재는 미커밋 후보·새 설치본 미검증 상태다. 위 최초 점검 내용은 당시 증거로 보존한다. 후속 회귀35건·타입·린트 통과와 상세 결정은 [모바일 통합 리뷰](MOBILE_INTEGRATION_REVIEW_2026-10-13.md)에 있다. 배포·제출은 하지 않았다. 다음 한 가지 행동은 후보의 로컬 Android APK 생성·데이터 유지 설치 검증이다.

## 후속 설치본 QA 완료 — 2026-10-13

[최종 QA 보고](MOBILE_FULL_QA_2026-10-13.md): 두 초안/사진 결함 수정, 최종 `.test` APK `2e9ebd73...`의 데이터 유지 설치 및16KB 홈 실행, 로컬 격리 API의 업로드/저장 왕복과 앱 초안·WebView 이력 검증 완료. 사용자 확정 범위의 Google/Naver/Kakao 로그인 화면 진입까지 확인했다. QA 앱/사진/서버/임시16KB AVD 데이터 정리, 원래 앱 데이터 유지. 본 단계는 실기기 GPS·실제 OAuth 완료·운영 API 쓰기·정식 AAB/스토어 설치·출시 증거가 아니다. 이전 표의 미확인 항목은 이 최종 보고와 시간/범위를 대조한다.
