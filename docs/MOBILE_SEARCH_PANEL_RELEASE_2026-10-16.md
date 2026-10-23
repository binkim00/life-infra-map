# 검색 목록 개선 — 비공개 테스트 1.0.4 (8)

## 정식 산출물

- 파일: `artifacts/local-builds/lifemap-production-code8-search-panel-20261016.aab`
- 크기: 72,101,005 bytes
- SHA256: `cc194a53f9b893d42a96567743dfe7b4b60430f94435be812cbce9dce374a9dd`
- 패키지: `com.binkim00.lifeinframap`, versionName `1.0.4`, versionCode `8`, minSdk24/targetSdk36, 회전 방향 제한 없음.
- 기존 Play 업로드 인증서 SHA256 `4df89b32c659cb77e964a57d1e646bc3c01027fedd5d931fddaa80f914301242` 일치, jarsigner 검증 통과. 새 키 생성·등록 변경 없음, 임시 키 정리.
- 네 ABI 각23라이브러리, R8 매핑 포함, 64bit ELF46개/LOAD140개 최소16384 정렬, BundleConfig `PAGE_ALIGNMENT_16K`, bundletool validate 통과.
- 서명 전후 서명 관련 항목 외1364 entry 내용 동일.
- Windows 짧은 native staging 캐시를 재사용한 로컬 `bundleRelease` 성공: 4분25초, 596 tasks 중84 실행. EAS 빌드/소스 업로드 없음.

## 포함 기능 및 검증

- 손잡이 드래그 세 단계 높이, 접힌 헤더 유지·목록 열기, 줄이기→기본, 중복 상세보기 정리, 상세 복귀 스크롤 보존, 가로 오른쪽 패널.
- 이전 관련 자동44검사 및 에뮬레이터 UI17확인 통과를 재사용했다. 버전 메타데이터 외 기능 소스의 추가 변경 없음.
- release sourcemap의 explore.tsx와 search-results-panel.tsx 원문이 에뮬레이터에서 검증한 현재 소스와 정확히 같음을 확인했다. 증거 `runtime/search-panel-release-20261016/embedded-sources.json`.
- 상세 화면 검증 범위는 `docs/MOBILE_SEARCH_PANEL_QA_2026-10-16.md` 참조. Play 설치본의 code8 실행이나 로그인·저장·사진 실업로드 전체를 새로 검증한 것은 아니다.

## Play 작업

- 시작 시 Alpha 1.0.3(7)은 선택 테스터에게 제공 중이며 게시되지 않은 변경사항 없음 확인.
- 기존 비공개 Alpha 트랙의 새 release4에 code8 업로드. 출시명 `1.0.4 (8) 검색 목록 개선`, 한국어 출시 노트 입력.
- Play가 code8의 업로드·배포 최적화를 완료하고 release4의 아티팩트로 수락했다. 매핑·native 기호 첨부 표시 확인. code8만 포함하고 기존 code7은 포함하지 않는 출시를 저장했다.
- 지원 기기 감소0: 전화12,313·태블릿6,500 유지. 신규 설치 예상17.5MB. 신규 경고0이라고 판정한 것은 아니다.
- 게시 개요의 미제출 변경1개는 비공개 Alpha `1.0.4 (8) 검색 목록 개선`의 전체 출시 시작이다. 관리형 게시가 사용 중지되어 있으므로 검토 승인 후 비공개 테스터에게 자동 게시될 수 있다. 프로덕션 공개 출시가 아니다.
- 최초 검토 전송은 자동 승인 심사에서 별도 직접 승인 요구로 중단됐다. 이후 사용자의 `code8 비공개 Alpha 검토 전송 승인`을 받고 기존 release4의 변경1개만 전송했다. AAB 재업로드 없음.
- 게시 개요의 `검토 중인 변경사항` 아래 Alpha `1.0.4 (8) 검색 목록 개선`과 `검토를 위해 변경사항 1개를 전송했습니다.` 접수 문구를 직접 확인했다. 현재 빠른 자동 검사 진행 중(최대12분 표시)이며 성공하면 Google 검토로 전달된다. Google 최종 승인·테스터의 code8 다운로드 가능 상태는 아직 확인되지 않았다.
- 접수 증거: `artifacts/local-builds/play-code8-review-submitted-20261016.jpg`. 게시 개요를 열어뒀다. 요청된 업로드·검토 전송 범위 완료. 다음 한 가지 행동: 사용자 상태 확인 요청 시 code8 최종 승인과 테스터 제공 여부를 확인한다.

## 경계

- 사용자 요청은 새 AAB 제작·기존 비공개 테스트 업로드. 프로덕션 공개 출시, 테스터 구성 변경, 초대 발송, Git 커밋·업로드·병합은 수행하지 않았다.
- 서버 제보 접수·사진 업로드 요청을 전송하지 않았다. 서버/DB/수집 서비스 변경 없음.
- 빌드·서명·검증 근거: `runtime/search-panel-release-20261016/{build.log,signature.json,verification.json,source-hashes.json,embedded-sources.json}`.
