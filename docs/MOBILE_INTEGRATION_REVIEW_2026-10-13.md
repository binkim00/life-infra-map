# 모바일 통합 후보·리뷰 — 2026-10-13

## 결과와 범위

현재 checkout에 **로컬 통합 후보**를 적용했다. 커밋·스테이징·checkout 전환·reset/clean/stash·원격 병합·빌드·배포·스토어 제출은 하지 않았다. mobile 밖 기능 파일은 변경하지 않았으며 다른 채팅의 backend/frontend/shared 수정은 보존했다. 이 결과는 설치본·출시 합격이 아니다.

기준 SHA: 현재 HEAD `6f1f8323cc87e3def055905a69e44c3af8322221`, release-foundation `5550de6532ae014ec6cbf923ebc0659097e1a2c2`, service-flow-verification `7d5b9a016ca362e07bc344c76fae237e86e0fe9c`. Git ancestor 검사에서 service-flow가 release에 포함됨을 현재 확인했다. 따라서 두 브랜치를 중복 적용하지 않고 base→release 변경과 현재 working copy를 3-way 비교했다.

보존·검토 자료: `runtime/mobile-integration-20261013/before/mobile/`에 수정 전 실제 파일, `candidate/mobile/`에 최종 후보, `manifest.json`에 refs·파일별 원본/최종 SHA256, `mobile-integration-review.patch`에 원본 working copy 대비 차이를 남겼다. native/node_modules/환경 파일/자격증명/빌드 산출물은 포함하지 않았다. 자료는 로컬 검토용이며 runtime 전체를 커밋하지 않는다. 원본과 후보는 62개 파일 범위이며 처음 적용에서 43개 파일을 변경하고 이후 리뷰 수정·검사를 추가했다.

## 충돌 결정

줄바꿈 CRLF/LF를 정규화한 실제 충돌9개를 해결했다. README의 최신 출시 점검 설명, 제보 목록의 중립 대표 이미지, 검색 카테고리 표시와 canonical UI를 유지했다. explore/recommend 저장 helper, route searchRequest 반복 검색, 로그인 복귀, JSON/사진 가입 구분, 초안/사진 첨부, 검사 모듈 경로 선택은 release/service 기능과 결합했다. 추천 화면의 generation unmount 무효화를 보존했다. 현재 수정의 안전한 비충돌 hunk를 자동 결합한 뒤 기능별 검토했다. 현재 파일 hash를 원본 snapshot과 대조해 동시 변경이 없을 때만 적용했다.

## 요청한 누락 확인

| 대상 | 최종 통합과 검증 |
|---|---|
| 저장 식별자 | `saved-place-payload.ts` 추가, explore/recommend 양쪽 사용. DB는 실제 placeId와 `local_db`, 외부 숫자 ID는 placeId=null, provenance보다 result_source 우선. 관련5검사 통과 |
| 계정 삭제 | account-deletion 화면·settings 링크·정책/지원 URL 복원. ID와 ‘계정 삭제’ 확인·사용자 확인창·POST 성공 뒤 로컬 인증 정리. authStorage 구독으로 AuthProvider도 갱신. 실제 삭제 실행 안 함 |
| 초안 복구 | use-form-draft owner key·직렬 저장/clear, 게시글 작성/수정·댓글/답글/신고·문의 연결. 기존 장소 제보 초안/이미지 처리는 유지. 재마운트·계정 분리·제출 후 이전 save 부활 방지 검사 통과 |
| 사진 | 가입·MY·게시글의 Expo File 첨부 유지. 게시글 사진 초안은 지속 저장 이미지 경로 사용. 새 설치본에서 실제 업로드는 미검증 |
| 인증/알림/등급 | refresh 오류 시 인증 보존·401 정리, 저장소 구독, 계정별 응답 guard와 현재 unread UI 유지. notification 설정·등급 색상/문구 service 기능 결합 |
| 공유 UI/출시 설정 | canonical shared helper·Metro watchFolders·공개3주소 정확 일치 guard 유지. backend/shared 자체 파일은 손대지 않음 |

## 리뷰 발견과 수정

- **P1 수정:** 같은 추천 화면에 새 route 검색이 들어올 때 기존 선택 장소 key가 React 이전 render closure로 요청에 실렸다. freshConversation 요청에서 selected_result_key를 제외하고 기존 detail/실패 재시도/chip/강조/위치 설명을 함께 초기화했다. 새 route generation이 바뀌거나 unmount되면 대기 중 session 후속 요청을 막는다. 기존 일반 후속 대화·오류 재시도는 선택 참조를 유지한다. 새 검색 회귀 검사 통과.
- **P1 수정:** 계정 삭제 응답 전에 다른 계정으로 전환되면 무조건 authStorage.clear가 새 계정을 로그아웃할 수 있었다. 요청 전 owner 확인, 성공 후 같은 owner일 때만 clear/홈 이동, 동기 중복 실행 guard를 추가했다. 다른 계정 보존 검사 통과. 실제 삭제·정책 변경 없음.
- 신규 account-deletion route로 기존 생성 타입이 오래돼 첫 tsc에서 오류가 났다. 설치된 Expo57 router-server 생성기로 `.expo/types`를 재생성했으며 타입 단언으로 우회하지 않았다. 불필요한 카테고리 import를 제거했다.
- 최종 검토에서 위 요청 범위의 재현된 미해결 결함은 없다. 화면별 실기기 동작·파일 초안의 OS 수명·서버 계약·계정 삭제의 백업/익명화 운영 증거는 자동 검사로 확정하지 않는다. 계정 삭제의 서버 정책은 기존 문구를 그대로 보존했다.

## 검사

- Node 모바일 회귀 **22/22**: 인증6, 초안1, 알림1, 네트워크6, 저장5, 등급/제보3.
- native adapter UX **13/13**: 기존9, 새 route1, 모의 계정 삭제3. 실제 POST/저장/사진 요청 없이 mock 검증.
- 최종 TypeScript·lint(경고0)·git diff whitespace 검사 통과. 타입 생성 후 재검사했다.
- Expo57 공식 문서와 설치된 typed-route 생성 소스를 확인했다. 네이티브 binary/실기기/Play 콘솔 재시험은 이번 통합 범위에서 실행하지 않았다.

## 남은 일과 다음 한 가지 행동

Git 후보는 현재 로컬·미커밋 상태다. 새 binary를 만들지 않았으므로 이전 Play code5 및 10/2 테스트 APK의 증거를 이 후보에 적용하지 않는다. 스토어 테스터0명/서명 대조/iOS 관련 차단은 출시 점검 보고서의 별도 조건이다.

**다음 한 가지 행동:** 이 후보의 로컬 테스트 APK를 생성해 연결된 Android 기기에서 데이터 유지 설치·설치 SHA와 핵심 흐름을 검증한다. 유료 EAS 빌드나 배포·스토어 제출은 포함하지 않는다.

## 후속 QA 수정·최종 설치본 — 2026-10-13

위 최초 리뷰 이후 설치본 QA에서 게시글 사진 제거 파일 잔류(P2), 같은 제보 대상의 계정간 저장 키 공유에 따른 초안 덮어쓰기(P1)를 추가 재현했다. 관리 사진 제거와 계정별 제보 키·소유자 확인 legacy 이동으로 수정했고 신규 관련5개 검사·타입/린트·설치본 재검증을 완료했다. 최초의 미해결 결함 없음/기기 미검증 문구는 당시 상태다.

[최종 QA 보고](MOBILE_FULL_QA_2026-10-13.md)에 댓글/답글/수정/신고·계정전환·사진3장/교체/삭제/로컬 실제 업로드·저장 식별자/해제·WebView 뒤로·16KB 및 공급자 로그인 화면 진입 결과를 기록했다. 최종 테스트 APK SHA256 `2e9ebd7386ea531fa3da32031416c824474b43b019802568096f414bd0414bf3`을 기존 테스트 앱에 데이터 유지 설치했고 QA 데이터는 정리했다. 공개 제보/배포/스토어 제출은 없다. 실제 OAuth 인증완료·물리 GPS·운영 업로드/저장 증거와 별도다.
