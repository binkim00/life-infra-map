# 모바일 전체 후속 QA — 2026-10-13 최종 보고

## 2026-10-14 정식 AAB 생성·등록 업로드 서명·16KB 검증 완료

사용자의146파일 Expo 전송 승인과 부모 채팅의 기존 등록 업로드키 재서명 직접 승인을 받아 작업을 마쳤다. 고정 master `c58d885c52ddf65095e1d28efb0fdc4015e6b9ba`의146파일로 EAS production 빌드 `a056e467-0a75-4d37-9436-75e43f097768` 성공, 2026-10-14 11:55:16~12:08:20 KST·네이티브 빌드 약12분57초. Free 플랜 사용3/30·현재비용0 확인. 공유소스/index/테스트 native/기기 자료를 보존했다.

**최종 Play 업로드용 로컬 파일**(업로드 자체는 하지 않음): `artifacts/local-builds/lifemap-production-code6-master-c58d885c-20261014.aab`,76,043,494bytes. SHA256 **`35c393f47f7adf8d435b3933da5cb202f5eb366f188329bc4fb18c0145981ae4`**. 패키지 `com.binkim00.lifeinframap`,1.0.2/code6·min24/target36,공개3endpoint 존재. jarsigner 내용 검증 통과·unsigned entry 경고 없음. 최종 업로드 인증서 SHA256 **`4df89b32c659cb77e964a57d1e646bc3c01027fedd5d931fddaa80f914301242`**로 부모가 직접 읽은 현재 Play 업로드키와 정확 일치한다. 배포용 앱서명 키54dce95a...와 구분한다.

첫 production 원격 버전 저장값은1이라code2가 예약됐고 즉시 취소/CANCELED 확인했다. 앞선code5 조회가.test를 기준으로 했던 문제를 수정해 production 기준을Play5에 맞춘 뒤code6을 생성했다. EAS 기본 production 키의 지문3e2147ad...가 등록키와 달라, 기존.test 명칭 자격증명에 보존된 실제 등록 업로드키4df89b32...를 찾았다. 해당 출처/production 사용은 자동 심사가 거절했고, 부모 채팅에서 사용자가 정확히 '기존 등록 업로드 키 사용·code6 재서명 승인'으로 직접 승인한 뒤만 진행했다.

원격 키 설정·Play 키·기존 원본키는 그대로 두고 완성code6 AAB의 서명만 로컬에서 정정했다. 개인키/암호/alias는 반환·문서화하지 않았고 작업용 임시 키 복사본은finally로 삭제했다. 서명 전후 **비서명1406개 entry의 SHA256 모두 동일**하여 앱 소스·패키지·code·manifest·native library는 유지됐다. 재빌드/새키생성/유료작업은 없다.

**16KB 산출물 검사 통과:** arm64-v8a/x86_64 ELF46개·LOAD140구간의 최소 정렬16384·미달0, BundleConfig `PAGE_ALIGNMENT_16K`, AAB ZIP integrity 정상. 공식bundletool1.18.3으로 만든 설치하지 않은 파생 검사용 APK의 압축하지 않은 native file92개 모두16KB ZIP정렬·zipalign36 `-c -P 16 -v 4` exit0·ZIP integrity 정상. 이 검사 APK는 기존 로컬 개발용debug키를 재사용했으며 새키 생성/설치는 없다. 최종 AAB 재서명 후1406개 내용hash동일 확인으로 기존ELF/파생ZIP 결과를 재사용했다. 실제16KB물리기기의 새정식설치본 런타임 증거와는 구분한다. 검사 기준은 [Android 공식16KB 가이드](https://developer.android.com/guide/practices/page-sizes) 및 [bundletool 공식 설정](https://github.com/google/bundletool/blob/master/src/main/proto/config.proto)이다.

**EAS 페이지의 원격 원본과 최종 로컬 파일은 다르다.** 원격 원본은 지문3e2147ad.../SHA `2e6ee1853281a6d0c312e9fce55e1747cc1311d079e3128cdd48995223ac537f`이며 `lifemap-production-code6-eas-original-20261014.aab`로 보존했다. 제출 후보는 위35c393f4.../등록키4df89b32...의 로컬 최종 파일이다. 원격 다운로드 원본을 최종 후보라고 부르지 않는다.

증거 `runtime/mobile-production-20261014/`: transmission-manifest.json, source-archive-audit.json, build-a056e467-0a75-4d37-9436-75e43f097768.json, final-aab-verification.json, apk-zip-verification.json, resign-candidate-entry-manifest.json. 기존 QA/테스트는 반복하지 않았다. Play 업로드·게시·제출·테스터초대·새키·결제·기기데이터삭제는 전부 하지 않았다. 테스터 안내/12명14일 참여 절차는 [별도 준비 문서](PLAY_TESTER_PREPARATION_2026-10-14.md)로 유지한다.

**다음 한 가지 행동:** 별도 Play 업로드 승인 후 최종35c393f4... AAB를 비공개 테스트 후보로 사용한다. 현재 요청의 빌드·서명·16KB 검증은 종료했다.

## 2026-10-14 최신 master 정식 AAB — 전송 후보 완료·명시적 Expo 승인 대기

사용자는 최신 수정 정식 AAB 생성과 서명검증을 요청했다. 원격 master를 읽어 `c58d885c52ddf65095e1d28efb0fdc4015e6b9ba`를 고정하고 workspace 독립 소스에 mobile/shared만 받았다. 공유 HEAD/index/native/dirty 작업·기기 데이터는 바꾸지 않았다. 기존 Node/EAS 및 모바일 의존성을 재사용했다.

Expo EAS 계정 `yeongbinkim`, 프로젝트 `life-infra-map`, projectId `c3a1fd87-d9e4-4b54-8702-c30fda27b86e`를 API 읽기로 확인했다. Free 플랜의 BUILDS 사용2/한도30, 현재 totalCost0이다. 원격 Android versionCode5를 직접 조회했고 production autoIncrement로 다음 code6을 사용할 계획이며 아직 예약하지 않았다. production 설정은 앱명 여기일지도, 정식 package `com.binkim00.lifeinframap`,1.0.2 및 공개3endpoint로 확인했다. 기존 원격 업로드키만 사용할 예정이고 새키/유료플랜/결제/스토어 업로드·제출은 하지 않는다.

검토 가능한 실제 source archive는 `runtime/mobile-production-20261014/master-c58d885c-mobile-production-source.tar.gz`다. mobile/shared146파일, 원문5,795,672bytes, 압축4,990,074bytes, SHA256 `f174328f14b74c76b4a2b13aa4110754b32829eb2a6a9a617a8331444c91fff6`. 압축을 읽어146개 일반 파일 각각의 SHA256 일치와 앱 entry/공유helper/package-lock/package/app.config/eas/metro 필수 파일 존재를 확인했다. Git line ending 정규화를 적용한 모든 blob은 고정 master와 일치한다. .git/node_modules/native android·ios/runtime/DB/APK·AAB/.env/credential/privatekey/기기 개인정보는 제외됐다. source-archive-audit.json·transmission-manifest.json에 전체 파일 및 전송 범위를 기록했다.

EAS inspect의 첫 Git 복사는 partial clone에서 실패했고, 공식 EAS_NO_VCS/EAS_PROJECT_ROOT 경로로 전환했다. 최초 whitelist가 디렉터리를 제외해 빈 archive를 만든 문제는 root whitelist를 고쳐 해결했다. 최종 archive는146파일로 검증 완료했으며 이전 빈 결과를 성공 증거로 재사용하지 않는다. EAS_NO_VCS 때문에 원격 Git 메타데이터가 없더라도 sourceSHA와146개 blob의 명시적 manifest/빌드 메시지로 출처를 고정할 예정이다.

정식 원격 빌드 실행은 자동 승인 심사가 'AAB 생성 승인만으로 비공개 소스를 Expo EAS라는 목적지에 보내는 직접 승인이 확인되지 않는다'고 거절해 실행되지 않았다. 우회/동일 재시도는 하지 않았다. 따라서 새 AAB/buildId/서명/16KB 성공 산출물은 아직 없다. 부모가 직접 읽은 현재 Play 업로드 인증서4df89b32...는 앞선 code5 AAB signer와 일치하지만 새 수정 AAB를 대신하지 않는다. 배포용 앱서명54dce95a...와 업로드키4df89b32...는 구분한다.

**다음 한 가지 행동:** 사용자에게 위146파일·4,990,074bytes를 Expo EAS의 명시 계정/프로젝트에 전송해 무료 production/code6 AAB를 기존 업로드키로 생성할 승인을 받은 뒤 빌드를 시작한다.

## 2026-10-14 실기기·출시 후속 — 서명 확인, 기기 접근 차단

부모 채팅은 사용자가 휴대폰 연결 가능이라고 답했고 실제 Android 연결을 확인했다고 전달했다. 이 채팅의 ADB 읽기 실행은 자동 승인 처리 deadline 시간 초과로 최초·1회 재시도 모두 실행되지 않았다. sandbox 기본 조회의 접근 가능 기기0은 휴대폰이 없다는 증거가 아니다. 익명 baseline 확인 스크립트 `runtime/mobile-physical-initial.py`를 준비했지만 실기기 OS/설치hash/UI/GPS 증거는 아직 얻지 못했다. 앱 설치/업데이트·계정/초안·위치 권한·사용자 화면 변경은 없다. 모의GPS로 대체하지 않았다.

새 읽기 증거: 기존 출시 code5 AAB에 JDK jarsigner를 실행해 exit0·jar verified·unsigned entries 경고 없음 확인. 인증서 SHA256 `4df89b32c659cb77e964a57d1e646bc3c01027fedd5d931fddaa80f914301242`. Self-signed/인증서 체인 경고는 공개 CA 신뢰 관련이며 AAB 내용 서명 실패와 구분한다. Play 업로드 인증서와의 일치 확인은 아직 없다. 기록 `runtime/mobile-physical-20261014/historical-aab-signature.json`.

현재 로컬 native 설정은 `.test / code4 / debug signing`이며 정식 package/업로드키를 사용한 새 수정 출시 AAB가 아니다. EAS production은 공개 endpoint·remote version·autoIncrement로 구성돼 있고 과거 code5 성공을 확인했지만, 로컬에 안전하게 사용할 기존 업로드키 접근과 출시 전용 native 경로를 확정하지 못했다. 새 유료 cloud build·서명키 생성·자격증명 출력 없이 여기까지 준비했다. 새 AAB가 필요하면 기존 업로드키를 비밀 출력 없이 연결하고 production package/native 설정을 격리된 build context에 적용해야 한다. 이 작업과 실제 서명키 접근은 별도 후속이다.

Play 콘솔 새 탭 생성도 자동 승인 deadline으로 실행되지 않아 이번 후속에서 release/정책/등록정보/인증서 상세를 새로 조회하지 못했다. 앞선10/14 직접 조회의 참여0·프로덕션 비활성 증거를 최신 확인 시점으로 유지한다. 과거 code5/target36/16KB 표시를 수정 APK 출시 증거로 바꾸지 않는다. 최소 잔여는 승인된 실행환경의 물리기기 baseline→키보드/뒤로/지도·실GPS, 콘솔 업로드키/앱서명키·release/정책/등록정보 읽기 대조, 콘솔12명14일 참여 조건이다. 실제 OAuth 완료·운영 업로드·공개 제출·계정 삭제·스토어 제출은 범위 밖으로 유지한다.

부모 채팅으로 종료보고 전송은 자동 승인 심사가 해당 목적지의 직접 사용자 승인 부족 및 내부 경로·인증서 정보 포함을 이유로 거절했다. 우회 전송하지 않았으며 결과는 이 문서와 현재 채팅에 남긴다.

**다음 한 가지 행동:** 사용자 승인이 확인된 실행환경에서 연결 휴대폰의 익명 baseline을 읽고 실기기 중요 흐름을 검증한다.

## 2026-10-14 최종 인계 — 모바일 수정 종료

두 결함 수정은 종료했다. 새 제품 수정 없이 최종 APK와 빌드 소스128개의 현재 SHA256을 대조했고 차이0이었다. 이미 통과한 빌드·테스트·설치본 QA는 반복하지 않았다. 최종 범위는 아래 제품 소스3개와 신규 검사2개이며, 다른 담당 변경이나 Git index/ref는 수정하지 않았다. 전체 통합 후보에는 이전 통합 변경도 별도로 보존해야 한다.

| 최종 파일 | SHA256 | 범위 |
|---|---|---|
| `mobile/src/components/post-editor.tsx` | `5db90c94ecbe04683a5cf10c5524a1ae507ec7bbd754b49b47ce33ed934abb31` | 사진 제거 시 관리 파일 삭제 |
| `mobile/src/app/place-report.tsx` | `f642c4e74a91f94e0ee806ea38fd5e79a111b6074f461d87214e03e103430075` | 계정별 제보 키와 소유자 확인 복구 연결 |
| `mobile/src/utils/place-report-draft.ts` | `4767f03b3fcae28a17b918affee6b5e5c5c98287c61c87ba013efb6ca01a6c75` | 소유자별 키·legacy 이동·사진 보존 |
| `mobile/tests/ux/audit-20261013.test.jsx` | `77b9ec34a1df4e7080a727bb73d76b2297ec52160c75bec17999c7b13179b0f0` | 실제 컴포넌트2검사 통과 |
| `mobile/tests/report-owner-draft.test.cjs` | `ff5e6b66017de1c8173560d067463f50992f4eb8ee4e003b67011fdcd3bc7c0b` | 계정분리·legacy·사진보존3검사 통과 |

고정 manifest: `runtime/mobile-full-audit-20261013/final-handoff-20261014.json`. 최종 테스트 APK는 아래 1.0.2/code4·SHA `2e9ebd7386ea531fa3da32031416c824474b43b019802568096f414bd0414bf3`와 동일하다. 기존 관련 타입/린트 검사 및5검사 성공은 재사용했고, 이번 변경의 diff 공백 검사도 통과했다.

읽기 전용 현황: 현재 연결된 실제 Android 기기0·에뮬레이터0. Play 콘솔을 직접 열어 출시 package의 비공개 테스트 게시 완료, 참여 선택0명, 프로덕션 비활성·신청 버튼 비활성을 재확인했다. 계정 자격증명 입력·동의·콘솔 저장·제출은 하지 않았다. 설치 사용자1명과 참여 선택0명을 혼동하지 않는다.

출시 AAB는 과거 code5 1.0.2 산출물이며 수정 테스트 APK와 별개다. 보존 AAB 경로 `C:/Users/SSAFY/.codex/worktrees/6180/life-infra-map/artifacts/lifemap-production-code5.aab`의 현재 hash는 `53eea938a2d25f4c5eec0e98716d9fcda732b0489777d42e96ea45266129da2c`로 과거 기록과 일치한다. 최신 수정2건이 이 AAB에 포함됐다고 주장하지 않는다. 당시 EAS 성공·Play code5/16KB 표시·AAB ELF 정렬 증거와 과거 code4 EAS 실패를 구분한다. 수정 APK의 유효 서명/16KB 실행은 확인했지만 AAB 서명 인증서와 Play 업로드키/앱 서명키 대조, 수정 코드의 새 출시 AAB·Play 설치본 검증은 미완료다.

외부 잔여의 최소 절차: 사용자 휴대폰 연결 후 기존 앱 버전·설치 hash를 읽고 실제 GPS 권한 거부/허용·좌표 취득을 확인한다. 운영 업로드는 현재 제출 금지 범위에서 보류하며 승인된 격리 업로드 대상이 마련돼야 한다. 실제 OAuth 완료는 이번 범위 밖으로 유지한다. 출시 준비는 통합 후보 확정 후 별도 요청에 따라 AAB/서명키 읽기 대조와 Play 설치본16KB 검증을 수행하고, 콘솔에 표시된12명/14일 참여 조건을 충족해야 한다. 공개 업로드·계정 삭제·배포·스토어 제출은 실행하지 않는다.

**다음 한 가지 행동:** Git 담당이 이5파일 hash와 기존 모바일 통합 변경을 함께 보존해 리뷰 가능한 통합 후보를 준비한다.

## 결과와 검증 범위

**합의한 에뮬레이터·로컬 격리 QA 검증을 완료했고, 결함2건을 수정했다. 테스트 데이터 정리도 완료했다.** OAuth는 사용자의 후속 답변에 따라 공급자 로그인 화면 진입까지만 확인했다. 제보 제출, 공개 게시글 제출, 운영 저장 데이터 변경, 배포·스토어 제출은 하지 않았다. 실제 업로드/저장 왕복은 loopback 전용 합성 fixture 서버에서 실행한 앱/전송 계약 증거이며 운영 서버 쓰기 성공과 구분한다. 물리 휴대폰 GPS·실제 OAuth 인증 완료는 주장하지 않는다.

| 항목 | 설치본에서 확인한 결과 | 판정 |
|---|---|---|
| 댓글·답글·수정·신고 초안 | QA 게시글의 댓글/답글/댓글 수정/게시글 신고/댓글 신고5종 값 저장·앱 종료 재실행 복구. 게시글 자체 제목/내용 수정 초안도 재실행 복구 | 통과 |
| 계정 간 격리 | 설치본 A→B→A 로그인: 게시글 상호작용·수정의 A 값 미노출 및 A 복귀 보존. 같은 제보 대상 A/B 각각의 초안 보존은 초기 실패를 수정 후 재검증 | 수정 후 통과 |
| 사진 여러 장·교체·삭제 | 제보 사진3장 관리 파일/해시/URI 재실행 복구,3장→1장 교체 후 이전 파일 삭제, 마지막 사진 삭제 및 재실행 빈 상태. 게시글 사진 제거의 실제 관리 파일 삭제·다른 사진 교체·재실행 복구 | 수정 후 통과 |
| 실제 사진 업로드 | Android 설치본의 게시글 작성 화면에서 실제 File/FormData multipart를 로컬 서버에 전송. 서버 수신 bytes/SHA256이 관리 사진과 정확 일치, 성공 후 초안/파일 제거. 생성한 로컬 게시글도 삭제 | 로컬 격리 전송 통과 |
| 검색 지도·카드·WebView 뒤로 | 원래 설치본 카드 expanded→peek→collapsed·다시 열기·상세 닫기·검색어 유지. QA HTTPS 상세1→2→Android 뒤로1 복귀와 상세 유지 | 통과 |
| 저장 식별자·저장/해제 | QA DB 후보 placeId7101/source local_db, 외부 숫자 ID91007102는 placeId=null/source kakao로 실제 요청. 각각 MY 표시·삭제 확인 및 서버 저장0 복귀. Spring controller의 camelCase 요청 field와 대조 | 로컬 격리 계약 통과 |
| 위치·16KB | 원래/최종 수정 공개 서버용 APK 모두 PAGE_SIZE16384 기기 설치 해시·홈·프로세스 확인.16KB QA 앱의 Android 모의 GPS/network 공급자 좌표를 실제 위치 API로 수신 | 모의 위치·16KB 실행 통과 |
| Google·Naver·Kakao OAuth | 각각 accounts.google.com/nid.naver.com/accounts.kakao.com의 공급자 로그인 화면. Google Sign in, Naver Sign in/Password, Kakao 계정/로그인 문구·입력칸2개/비밀번호칸1개 확인. 자격증명 입력·동의·ticket 교환 없음 | 요청한 화면 진입 범위 통과 |

원래 에뮬레이터 GPS 입력만으로는 새16KB 기기에서 위치를 받지 못했다. OS 모의 공급자에서 전달한 위치를 앱에서 받는 경로를 별도로 확인했으며 이 결과는 물리 GPS나 에뮬레이터 GNSS 정확도 증거가 아니다. WebView 첫 확인은 로컬 HTTP를 앱이 HTTPS로 승격해 시험 페이지가 실패했다. 제품 정책을 바꾸지 않고 QA APK에만 로컬 인증서 신뢰를 넣어 HTTPS fixture로 검증했다. 첫 뒤로 직후 접근성 snapshot에서 링크가 안 보였지만 후속 snapshot의 첫 페이지 제목과 상세 닫기 버튼으로 실제 이력 복귀를 확인했다.

## 수정한 결함

1. **P2 게시글 사진 제거 후 파일 잔류:** `mobile/src/components/post-editor.tsx`의 사진 제거를 `removeImage` 처리로 연결했다. 첨부 상태를 비우고 기존 `removeDraftImages`로 관리 파일만 삭제한다. 모의 재현은 호출0→호출 확인, 설치본에서는 실제 경로의 파일 부재까지 확인했다.
2. **P1 같은 제보 대상의 계정별 초안 덮어쓰기:** 이전 제보 키는 소유자 표시만 가지고 저장 키를 공유했다. A 작성→B 작성→A 복귀에서 A 초안 보존 실패를 설치본에서 재현했다. `ownedReportDraftKey`로 계정별 키를 나누고 `loadOwnedPlaceReportDraft`로 소유자가 맞는 기존 v2 초안만 새 키로 이동한다. 이동 시 사진 파일은 지우지 않으며 외국 소유자의 기존 초안은 건드리지 않는다. 이전 anonymous 초안은 기존 정책대로 첫 로그인 소유자가 이어 쓴다. 수정된 APK의 동일 A/B 시나리오에서 각 초안 보존·미노출을 재확인했다.

검증: 새 실제 컴포넌트2개 검사 모두 통과, 계정 분리·legacy 이동·사진 보존의 신규3개 검사 모두 통과. 관련 TypeScript·3파일 ESLint·whitespace 검사 통과. 기존 다른 모바일 변경과 비대상 작업을 보존했다. 커밋/푸시는 하지 않았다.

## 최종 산출물과 데이터 유지 설치

- 최종 공개 서버용 테스트 APK: `artifacts/local-builds/lifemap-test-fixed-20261013.apk`,108,301,442 bytes,1.0.2/code4·min24/target36, offline 빌드1m35s 성공.
- SHA256 `2e9ebd7386ea531fa3da32031416c824474b43b019802568096f414bd0414bf3`; 검증된 서명 인증서 SHA256 `fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c`.
- 공개 Django/Spring/지도 주소3개 존재, QA loopback18765/18766 문자열과 QA 인증서/네트워크 설정 리소스는 없다.128개 최종 소스 hash를 기록하고 빌드·QA 후 변경0 확인. source fingerprint `d02e2d4bebb29d9335d346ea392d7ad1e4704f0639a5ab960a2a8622c470fe01`.
- 기존 emulator-5554의 `.test` 앱에 install -r 성공, 설치 base APK hash 일치. appId10217/CE567078/DE393755/최초 설치2026-09-30 11:34:42 KST(기기 원문02:34:42 UTC) 유지. 이는 OS 데이터 디렉터리/설치 정보 보존이며 모든 기존 개인 데이터 값을 원문 비교한 증거는 아니다.
- 최종 APK도16KB 기기에서 실제 홈 표시·프로세스·설치 hash 확인했다. QA APK들은 별도 `.qa` 패키지이며 TLS판은 SHA `9c0b8da981a8c6f96b0c92b3afd0c9794d45f5fded543bfeeb353241d2f81e47`; 이 변형의 로컬 서버 설정/신뢰는 제품 APK에 들어가지 않았다.

## 정리와 보존

- 로컬 서버 저장 장소0, 생성한 업로드 게시글 삭제 후 초기 fixture 게시글1개로 복귀 확인. 서버 종료로 메모리의 합성 fixture·업로드 바이트를 해제했다.
- 두 시험 기기의 `.qa` 패키지를 제거해 합성 계정·초안·관리 사진·ImagePicker/WebView 캐시를 정리했다. 기존 emulator-5554 `.test` 앱은 최종 수정본과 기존 데이터로 유지했다.
- 기존 갤러리는 유지하고 검증한 QA_FULL_1013_1/2/3 파일과 MediaStore 행만 제거했다.
- 새16KB 기기의 모의 GPS/network 공급자와 shell mock 권한을 복원하고 종료했다. 직접 만든 workspace AVD의 경로/식별자를 확인해 기기 데이터도 제거했다. 임시 QA 서버와 인증서 private key는 종료/삭제했다. 공식 SDK 시스템 이미지는 재사용 가능한 설치 도구로 남긴다.
- host의 APK·소스 hash·합성 테스트 이미지·QA 화면·개인정보 없는 요약은 재현 증거로 보존했다. 실제 토큰·비밀번호·브라우저 nonce/전체 URL·개인 사진은 출력/저장하지 않았다.

## 증거

`runtime/mobile-full-audit-20261013/`의 native-account-draft-evidence.json, native-post-edit-evidence.json, native-report-owner-before-fix.json/native-report-owner-evidence.json, native-photo-preupload-evidence.json/native-photo-evidence.json, native-multiple-photo-evidence.json, native-saved-web-evidence.json, native-gps-16kb-evidence.json, oauth-*-entry.json, public-fixed-apk.json, public-fixed-install.json, public-fixed-16kb.json, cleanup-final.json 및 component-test-results-after-fix.json. 첫 단계 중간 보고서는 phase1-report.md로 보존했다.

**다음 한 가지 행동:** 후속 요청이 있을 때 최종 테스트 APK와 이번 검증 증거를 기준으로 실기기 또는 실제 OAuth 완료 범위를 검토한다.
