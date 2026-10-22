# M2 계정 삭제 경합 — master 기반 격리 후보 검증

master `9ab7e232ddb9049210caaad9e384a09a76084b08` 위에 정확히 2파일만 반영한 격리 후보를 구성했다. 최종 Git tree는 `723f679b15b18e4fcfb8170e7f7477ce10b6277c`다. 실제 commit/branch 생성·push·PR·계정 삭제·운영 배포는 하지 않았다.

| 대상 | master 대비 변경 | 내용 |
|---|---:|---|
| mobile/src/app/account-deletion.tsx | 12행 추가 / 3행 삭제 | 처리 중 중복 실행 guard, 요청 전 owner 확인, 응답 후 같은 owner일 때만 인증 정리·홈 이동 |
| mobile/tests/ux/account-deletion.test.jsx | 신규 31행 | 잘못된 확인 입력·실패/성공·응답 전 계정 전환·처리 중 중복 확인·요청 직전 계정 전환 mock 5개 |

삭제 화면은 공유 미커밋과 같은 내용이다. 검사 파일은 기존 공유 mock 3개에 의미 있는 경합 회귀 2개를 격리 후보에서 추가하고 import 순서를 정리했다. 공유 검사 파일에는 이 추가/정리를 적용하지 않았다. 총 43행 추가·3행 삭제이며 다른 파일은 master 내용을 유지한다. authStorage·AuthProvider·API client·settings·삭제 API 정책·검색 UI 변경을 추가로 가져오지 않았다.

## 확인 결과

- 계정 삭제 native adapter mock **5/5 통과**, 실패·제외0, 최종 2.77초. 실제 POST·인증 저장소·화면 탐색은 mock으로 대체했다.
- master 기반 인증 client의 관련 Node 회귀 **6/6 통과**, 실패·제외0. 갱신 시간 초과/오류 시 세션 보존, 만료 인증 정리, 갱신 성공, 느린 조회 재시도, 작성 요청 중복 방지를 확인했다.
- 격리 full-mobile TypeScript `--noEmit` 검사 진단0. 기존 생성 router 타입을 검사 harness에 복사했다. 최종 추가 수정은 JSX 검사 import 순서뿐이므로 동일 TypeScript 검사를 반복하지 않았다.
- 삭제 화면·mock 검사 파일 lint 오류0/경고0. 변경 Python은 없으며 Git diff whitespace·master 기준 patch 적용 검사 통과.

mock 5개는 확인 전 요청하지 않음, 틀린 입력 차단, 서버 실패 시 인증 보존, 같은 계정 성공 시 한 번 정리/홈 이동, 응답 전 전환된 계정 보존, 대기 요청에 확인을 반복해도 API/정리 한 번, 확인창 뒤 요청 직전 계정이 바뀌면 API 미호출을 확인한다. 외부 삭제 API·운영 계정·실기기 삭제를 실행하지 않았다.

## 환경과 해석

master의 mobile/shared만 runtime에 추출하고 기존 모바일 dependency를 읽는 junction을 검사 harness에 연결했다. mock 실행에는 기존 웹의 Vitest 4.1.10·React testing dependency 경로를 명시했다. router 생성 타입·junction·lint harness는 후보 Git tree에 포함하지 않았다. 클린 dependency 설치 또는 원본 npm 명령만으로의 재현 검증은 아니다.

최초 mock 실행은 sandbox 임시 캐시 rename EPERM으로 검사 시작 전에 실패했다. 동일 격리 후보에서 허용된 실행 환경으로 재검사해 통과했다. 최초 lint는 mobile에서 웹에 설치된 testing-library/Vitest import를 찾지 못했고 import/first 경고도 있었다. 후보 검사 import 순서를 수정하고, 기존 웹 dependency를 찾도록 runtime 전용 lint resolver를 설정해 최종 오류·경고0을 확인했다. 제품 lint 설정과 dependency는 변경하지 않았다.

이 검증은 앱의 요청/로컬 인증 경합 방어를 확인한다. 실제 서버 삭제·백업 만료·익명화 정책, native 빌드/기기 흐름, 운영 배포 완료의 증거가 아니다. 이번 5개를 이전 앱 전체 UX13개 통과로 확대하지 않는다.

## 증거와 보존

- [고정 manifest](../runtime/m2-master-candidate-20261013/manifest.json)
- [master→후보 patch](../runtime/m2-master-candidate-20261013/change.patch)
- [검사·보존 audit](../runtime/m2-master-candidate-20261013/checks.json)
- [mock 출력](../runtime/m2-master-candidate-20261013/mock-tests.txt), [인증 회귀 출력](../runtime/m2-master-candidate-20261013/auth-tests.txt)
- [병합된 삭제 화면](https://github.com/binkim00/life-infra-map/blob/0450db570fbcf07a28ee5bccd94349f744c7e4b3/mobile/src/app/account-deletion.tsx), [병합된 mock 검사](https://github.com/binkim00/life-infra-map/blob/0450db570fbcf07a28ee5bccd94349f744c7e4b3/mobile/tests/ux/account-deletion.test.jsx)

검사 시작 시 기록한 공유147코드 hash 변경0, HEAD `6f1f8323`·공용 index hash 유지·staged0을 확인했다. 공통 Git 상태와 본 검토 문서만 갱신한다. 새 master 기반의 이번 후보 구성·검사에서 재현된 미해결 차단 문제는 없다.

**다음 한 가지 행동:** 검토된 M2 고정 tree를 독립 커밋·draft PR로 준비한다. 이번 요청에서 commit/push/PR은 실행하지 않았다.
