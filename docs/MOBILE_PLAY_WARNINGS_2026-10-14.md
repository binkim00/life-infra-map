# Play code6 최적화와 화면 경고 수정

## code7 정식 AAB 재업로드·검토 요청 완료

- 사용자 재업로드 승인으로 1.0.3/code7 정식 AAB를 만들었다. Windows native 객체 경로 한도로 기존 네 ABI 빌드가 실패했으나, Windows 전용 native staging 디렉터리를 짧게 옮겨 CMake의 실제 객체 경로 해시 생성을 확인하고 4분57초에 빌드했다. 128 한도만 강제한 실패 설정은 제거했다. 기기 지원을 줄이지 않았다.
- 최종 [정식 AAB](../artifacts/local-builds/lifemap-production-code7-screen-api-20261014.aab): 72098960bytes, SHA256 21cde2a2c07a8b2ebac2497f4ce21c090113c2d0e413418060a80111372a0224. 기존 등록 업로드 인증서 4df89b32...14301242로 재서명·검증, 임시 키 정리. 키 생성·설정 변경은 없었다.
- package com.binkim00.lifeinframap/1.0.3/code7/min24/target36/방향-1/네ABI각23라이브러리/R8mapping 포함 확인. 서명 외1364 entry 내용 동일, 64bit ELF46개·LOAD140개 최소정렬16384 및 BundleConfig PAGE_ALIGNMENT_16K·bundletoolvalidate 통과. 상세 JSON은 ignored runtime/mobile-play-warnings-20261014/production-code7-verification.json.
- Play가 Alpha releases/3의 업로드를 실제 수락했다. ReTrace 매핑과 native 디버그 기호가 첨부된 것으로 표시됐다. 지원 기기 감소0, 전화12297/태블릿6493 유지. Google 예상 설치크기17.5MB로 이전보다11.6MB 감소 표시. 이는 Play의 추정치이며 모든 기기의 실제 크기를 보장하는 수치는 아니다.
- code7만 포함한 100% Alpha 출시·한국어 개선 노트를 저장하고 변경1개를 검토 전송했다. 최종 게시개요에 검토 중인 변경사항·1.0.3(7) 비공개 테스트·전체 출시 시작을 확인했다. 빠른 자동검사 통과 후 검토 전송 예정이며, 기존 관리형 게시 사용중지 설정 때문에 승인 후 자동 게시 대상이다. 승인·실제 code7 테스터 제공은 아직 확인하지 않았다.
- [전송 확인 화면](../artifacts/local-builds/play-code7-review-20261014.jpg)을 저장하고 열린 게시개요를 유지했다. 현재 Play의 경고3개가 code7 재분석으로 해소됐다는 확인은 아직 없으므로 경고0이라고 보고하지 않는다.
- 서버 QA 제보 접수·테스터 초대 발송·프로덕션 공개 출시·Git 반영·EAS 소스 전송은 없다. 다음 EAS 빌드에서는 이미 Play에 사용한7보다 큰 버전 코드인지 확인해야 한다.
- 다음 한 가지 행동: Google 처리 후 Alpha code7 실제 제공과 최신 Play 경고 재분석 상태를 확인한다.

## Android15 이후 라이브러리 호출 보완·새 APK 검증

- 기존 Expo release 플러그인에서 AGP의 ASM instrumentation으로 prebuilt RN 0.86.2 바이너리를 보완했다. StatusBarModule/색상 runnable/WindowUtilKt에 한정해 SDK35 이상 구형 Window 색상 setter를 건너뛰고 상태 표시줄 색 getter는 투명색을 반환한다. SDK24~34는 기존 호출·인자를 유지하며, 테마·insets·아이콘·대비 처리는 유지한다. RN 버전 변경 시 prebuild가 실패하도록 검토 조건을 두었다. node_modules 원본·최소 지원 버전은 유지했고 반사 호출로 경고를 숨기지 않았다.
- mobile/plugins/android-api-guards/tests에서 변환된 JVM 바이트코드를 실제 실행해 SDK24/28/34의 기존 setter/getter·인자·결과 보존, SDK35/36의 구형 호출0회·투명색 결과를 검증했다. 5/5 통과. 하위 Android 실기기 검증과 구분한다.
- native 클래스 로더 의존성과 Metaspace 부족을 해결한 후 격리 JDK17 빌드(-Xmx4096m/MaxMetaspaceSize1024m)에서 release R8 성공(5분12초,561tasks). 실제 변환 RN jar의 SDK35 분기, 최종 DEX RN Window 호출7개 각각의 SDK 조건을 확인했다. 최종 분석이 단순 소스 변경 확인을 대신한다.
- 새 APK artifacts/local-builds/lifemap-screen-api-guard-test-20261014.apk: 35364993bytes, SHA256 7a92126d3b94b05bf0c2e2488c8d719c2391193267f1403c63c74b476d8f5c42. 기존 .test 인증서 fac61745... 검증·install -r 성공·기기 base APK hash 일치·firstInstallTime 2026-09-09 유지. 이전 APK는 별도 파일로 보존했다.
- Android16 실기기에서 앱 시작/지도WebView/화장실 검색 응답·결과 상세 버튼/가로 필터 왼쪽·결과 오른쪽/보관함0곳/MY로그인/동일QA사진초안1/3 유지 확인. 빈 보관함 화면을 시각 검토해 표시줄·하단탭 겹침 없음을 확인했고 회전0/자동회전1을 복원했다. 해당 프로세스 최근 로그 치명적 예외0. 사진 선택기를 다시 열거나 서버 제보를 접수하지 않았다.
- 저장 생성·해제 왕복과 Node25/UI17/타입/lint는 이전 APK에서 확보한 증거를 재사용한다. 이번에는 JS 논리 변경이 없었다. 새 소셜 로그인 전체·태블릿·하위 Android 실기기 시험·추가 서버 쓰기는 하지 않았다.
- **완료 범위:** SDK35+ RN 호출 보완과 위 새 APK 검증. **확인 대기:** 하위 버전 호환용 구형 참조는 DEX에 남는다. Play의 현재 code6는 이전 파일이므로 Play 경고0·DEX최적화25%는 새 정식 AAB의 Play 재분석 전 확정할 수 없다. 이번 production AAB 생성·등록 키 사용·Git/EAS/Play 전송은 없다.
- 증거: ignored runtime/mobile-play-warnings-20261014/native-api-guard-self-test.json, instrumented-statusbar-bytecode.txt, instrumented-windowutil-bytecode.txt, final-rn-api-guards.json, guard-device-verification.json 및 guard-apk-*.xml/png. 개인 화면 원문은 외부 공유하지 않는다.
- 기준 자료: [Android15 화면 동작 변경](https://developer.android.com/about/versions/15/behavior-changes-15), [RN0.86.3에도 남은 호출](https://raw.githubusercontent.com/facebook/react-native/v0.86.3/packages/react-native/ReactAndroid/src/main/java/com/facebook/react/views/view/WindowUtil.kt), [AndroidX Splash의 SDK33 미만 테마 복원](https://raw.githubusercontent.com/androidx/androidx/androidx-main/core/core-splashscreen/src/main/java/androidx/core/splashscreen/SplashScreen.kt). 안정 패치 업그레이드만으로 이 호출 제거를 보장할 수 없다고 판단했다.
- 다음 한 가지 행동: 수정 소스를 포함한 정식 AAB를 준비해 Play 재분석 대상으로 구체화한다. 로컬 APK 검증을 현재 Play 경고 해소로 표시하지 않는다.

## 사진 초안·저장 해제 후속 실기기 검증

- 사용자가 선택한 QA 사진 1장을 첨부했다. 다른 화면으로 이동한 뒤 동일 QA 제보 초안을 다시 열고 스크롤해 `사진 선택 (1/3)`과 `첨부 사진 삭제`를 확인했다. 사진 선택·첨부·초안 복원 검증은 통과했다.
- 사용자가 서버 접수를 명시적으로 거절했다. `제보 접수`를 누르지 않았으며 사진의 실제 서버 업로드·검토 대기 접수는 검증하지 않았다. QA 초안은 기기에 남아 있다.
- `희망공원 공중화장실`을 이번 검증에서 새로 저장하고 보관함을 다시 불러와 해당 행을 확인했다. 그 행만 삭제 확인창에서 해제한 뒤 홈→저장으로 재조회해 `0곳`과 해당 행 부재를 확인했다. 기존 빈 보관함으로 복원했다.
- 증거: ignored runtime/mobile-play-warnings-20261014의 saved-created-refreshed.xml, saved-removed-refreshed.xml, photo-draft-restored-scrolled.xml. 개인 화면 원문은 외부 공유하지 않는다.
- 최종 DEX에서 Window 색상 API 실제 호출 15개를 확인했다. RN StatusBarModule·WindowUtilKt, Material datepicker, AndroidX splash, ExpoCropImageActivity 및 react-native-screens FormSheetDialog가 포함된다. Expo 사진 자르기 소스는 이미 WindowCompat.enableEdgeToEdge를 사용하지만 하위 버전 호환 구현이 최적화 과정에서 호출 위치에 들어간다. 메서드 참조만 제거하는 변경은 호환성을 보장하지 않는다.
- 이번 후속 확인으로 새 APK·production AAB·Play 업로드를 만들지 않았다. 화면 API 경고 제거는 여전히 미완료다.
- 다음 한 가지 행동: RN의 기존 버전과 호환되는 upstream 화면 API 수정의 적용 범위를 확정한다. prebuilt RN AAR에 반영되는 빌드 경로와 하위 Android 검증 없이 node_modules 소스만 바꾸고 해결됐다고 표시하지 않는다.

## 후속 검증 결과

- JDK17 및 짧은 같은 드라이브 qa14 검증 경로로 Windows Java/CMake 경로 오류를 해결했다. Material 1.14.0 안정 버전 제약을 플러그인에 추가했고 실제 의존성 수신·release R8 빌드 성공을 확인했다. 최초 성공 6분18초, 가로 수정 재빌드 2분12초다.
- Android16 실기기에서 가로 검색 결과 패널이 거리 필터를 덮는 결함을 발견했다. explore.tsx의 useWindowDimensions로 가로 상태를 감지하고 검색·필터를 왼쪽, 결과를 오른쪽에 배치했다. 최종 APK에서 1/3/5/10km와 검색·카테고리·결과가 각각 도달 가능한 bounds를 확인했다.
- 최종 artifacts/local-builds/lifemap-play-warnings-fixed-test-20261014.apk: 35364997bytes, SHA256 6a6836d849bb31dd6c8893c19fb1702e47e82039168b41144f57ef46cb4c83eb, 기존 .test debug 인증서 fac61745... 일치. install -r 성공·기기 실제 base APK hash 동일·firstInstallTime 유지. 정식 앱과 사용자 기존 데이터 보존, 회전 설정 복원, 임시 R드라이브 연결 정리.
- 실기기 확인: 로그인된 MY 세션 유지, 홈 주변 결과, WebView 지도, 화장실 필터 검색 응답과 장소 상세 진입, Android 뒤로 복귀, 저장 목록 열기, 가로 제보 폼 스크롤, 실제 시스템 사진 선택기 열기·취소. 개인 사진 선택·새 OAuth 로그인 전체 과정·제보/게시 제출·저장 생성/해제 왕복·태블릿은 이번 증거에 포함하지 않는다.
- 가로 수정 후 타입·lint·UI17검사 재통과. 앞서 Node25검사는 불변 영역으로 반복하지 않았다.
- R8 mapping/usage 및 DEX 분석 증거: runtime/mobile-play-warnings-20261014/r8-verification.json/apk-native-inspection.json. 로컬 클래스 이름 변경 비율은 Google Play의 DEX 최적화 비율과 다르므로 Play25% 달성이라고 주장하지 않는다.
- **잔여 항목:** 최종 APK에 Window get/setStatusBarColor 및 get/setNavigationBarColor 메서드 참조가 남았다. Material 대응·edge-to-edge 설정은 적용했지만 RN/AndroidX 하위 Android 호환 코드까지 제거되지 않았다. Play 화면 API 경고 0개 달성은 미완료이며, 라이브러리 참조를 반사 호출로 숨기거나 Android 지원 버전을 올려 경고를 피하지 않았다. 이번 APK는 로컬 테스트 패키지이며 새 production AAB·Play 업로드는 없다.
- 다음 한 가지 행동: 잔존 호출의 최종 DEX 호출 위치·Android 버전 분기를 분석해 RN/AndroidX의 안전한 수정 범위를 정한다. 이를 마치기 전 전체 3경고 해결 완료로 표시하지 않는다.

## 확인한 사실

- Play의 사용자 열린 테스트 및 출시 화면을 직접 읽었다. code6 Alpha 제공 시간 21분 전, 게시되지 않은 변경사항 없음으로 표시됐다. 이전 심사 대기 기록보다 최신이다.
- DEX 난독화 1% 경고와 2027년 2월 기한이 표시됐다.
- 화면 API 시작 위치는 React Native StatusBarModule·WindowUtilKt와 Material BottomSheetDialog·EdgeToEdgeUtils·SheetDialog이다. 앱이 직접 구형 색상 API를 호출한 것으로 오인하지 않는다.
- 방향 경고의 정확한 대상은 MainActivity의 screenOrientation=PORTRAIT이다.

## 수정

- mobile/app.json의 orientation을 default로 바꿨다. 휴대전화에서도 회전할 수 있으므로 세로·가로 기능 검증이 필요하다.
- mobile/plugins/with-android-release-optimization.js를 등록했다. 기존 expo/config-plugins를 사용해 Android release minify와 resource shrink, edge-to-edge를 설정하고 기본 ProGuard 파일을 optimize 버전으로 바꾼다. 새 의존성·포괄적인 keep 규칙·경고 숨김은 추가하지 않았다.
- 공유 android 디렉터리 대신 runtime/mobile-play-warnings-20261014에서 prebuild했다. 실제 생성 파일에 세 속성 true, optimize ProGuard 파일, MainActivity screenOrientation=unspecified를 확인했다.

## 검증과 한계

- 기존 기능 Node 검사 25/25, 모바일 UI 검사 17/17 성공. 인증 갱신·초안 계정 분리·저장 payload·재시도와 대화·계정 삭제·알림·사진 관련 UI 회귀를 포함한다.
- TypeScript 검사와 lint 성공. 첫 UI 검사·prebuild는 Windows 파일 권한에서 실패했으며 허용된 로컬 권한으로 재실행한 검사가 통과했다.
- 별도 경로에서 기존 캐시로 release APK 빌드를 시작했다. 실행 식별자는 exec session 10177, 로그 runtime/mobile-play-warnings-20261014/mobile/native-release.log다. 완료 APK·R8 mapping 및 최적화 비율은 아직 미확인이다.
- 이번 수정 APK의 실제 기기 설치·로그인 완료·지도 동작·사진 선택·가로/태블릿 동작은 아직 검증하지 않았다. 기존 자동 검사가 새 native APK의 기능 정상 증거를 대신하지 않는다. ADB는 sandbox 서버 시작 실패였고 사용자 기기 데이터는 변경하지 않았다.
- React Native/Material 호환 코드에 구형 API가 남아 있다. edge-to-edge 설정만으로 Play 정적 경고가 사라진다고 주장하지 않는다. R8 산출물에서 남은 클래스와 호출을 확인한 뒤, 유지되는 호출은 라이브러리 수정·업데이트와 하위 Android 호환성을 함께 검토해야 한다.
- code6 파일/Play 배포는 변경하지 않았다. Git 업로드·새 EAS 소스 전송·새 Play 제출은 실행하지 않았다.

## 다음 한 가지 행동

별도 release APK 빌드 결과를 확인해 R8 산출물과 잔존 화면 API를 검사하고, 그 APK로 실제 기기 회귀 검증을 이어간다.


## 2026-10-23 미커밋 Android 작업 분리 검증

- Expo 설정에는 릴리스 최적화 플러그인 등록만 포함. 버전/방향 변경은 검색 패널 작업으로 분리한다.
- 현재 Java 원본을 기존 Gradle/ASM 캐시로 컴파일하고 변환 바이트코드를 실행해 SDK 24/28/34/35/36 다섯 경우 모두 통과. 플러그인 JS 구문 검사 통과.
- 기본 제한 환경에서는 javac 실행이 시간 초과되어, 권한이 허용된 분리 작업 폴더에서 동일 소스를 컴파일/검사했다.
- 이번에는 AAB 재빌드·실기기·Play 경고 재검사·업로드를 하지 않았다. 과거 경고/기기 검증 한계는 유지한다.
- 근거: 원본 작업 폴더 runtime/uncommitted-audit-20261023/java-guard/{compile,result}.txt.
