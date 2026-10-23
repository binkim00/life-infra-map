# 모바일·웹 검색 UX 수정 보고

2026-10-06. 로컬 구현·자동 검증 완료. 운영 배포와 실기기 수동 검증은 실행하지 않았다.
검색 알고리즘, Evidence ranking, FastAPI 전환, AI Web Search 실행 정책은 이번 수정의 완료 근거에 포함하지 않는다. 같은 checkout의 다른 검색 작업 변경을 보존했다.

## 1. 수정한 UX 문제

- 새 대화를 모바일 고정 입력 영역, 웹 화면 고정 버튼으로 제공한다. 최소 터치 높이는 44px이다. 초안·조건·결과가 있을 때만 확인한다. 모바일은 확인창·세션 생성·turn의 중복 요청을 막는다.
- 대화 generation을 바꾸면 이전 turn/참고 검색 응답을 무시한다. 웹은 지도 준비 이후에도 generation을 확인한다.
- 상세·패널을 닫아도 검색 상태를 지우지 않는다. 실패 시 입력·세션·canonical 조건·기존 결과를 유지하며 같은 요청으로 재시도한다.
- 결과 패널 3단계, 마커와 카드의 provider별 stable key, 카드 스크롤·선택 표시를 연결한다.
- 서버 조건 chip과 구조화 clarification action/value를 표시한다. 설명·비교 답변은 기존 리스트와 서버 참조 카드에 연결한다.
- 홈 공원 고정 검색·이미지를 제거한다. 현재 위치 서버 결과를 여러 카테고리로 표시한다. 위치 실패와 검색 실패를 구분하고 재시도에서 위치 재획득·검색을 실행한다.
- 카테고리별 대표 이미지/아이콘에 대표 이미지 표시를 붙였다. 미분류는 중립 아이콘이다.
- 실제 unread와 계정/설정에 따른 알림 점, 사용자 제보 DTO 정리, 사용자 오류 문구 정리를 적용한다.

## 2. 모바일·웹 수정 파일

### 모바일

- 화면: `mobile/src/app/(tabs)/recommend.tsx`, `explore.tsx`, `index.tsx`, `_layout.tsx`, `mypage/reports.tsx`, `mypage/index.tsx`, `mypage/saved-places.tsx`; `mobile/src/app/_layout.tsx`, `notifications.tsx`, `place-report.tsx`, `login.tsx`, `signup.tsx`.
- 공통 화면: `mobile/src/components/screen.tsx`, `place-detail-sheet.tsx`, `place-map.tsx`, `place-map.web.tsx`, `place-photo.tsx`, `report-detail.tsx`.
- 상태/통신: `mobile/src/hooks/use-notifications.ts`, `use-action.ts`, `use-resource.ts`; `mobile/src/utils/back-navigation.ts`, `place-identity.ts`; `mobile/src/api/client.ts`, `request-retry.ts`, `recommendations.ts`; `mobile/src/auth/auth-context.tsx`.
- 검사: `mobile/tests/ux/conversation.test.jsx`, `notifications.test.jsx`, `setup.jsx`, `mobile/vitest.ux.config.mjs`, `mobile/package.json`의 `test:ux`.

### 웹

- 검색: `frontend/src/views/HomeView.jsx`, `MapSearchView.jsx`, `MapSearchView.module.css`, `home/PlaceResultList.jsx`, `home/AiWebSearchPanel.jsx`; `frontend/src/styles/SearchUx.css`; `frontend/src/hooks/useHomeSearch.js`, `homeSearchState.js`, `useOverlayHistory.js`, `usePanelHistory.js`.
- 알림/저장: `frontend/src/hooks/useNotifications.js`, `useSavedPlaceActions.js`.
- 표시 도우미: `frontend/src/utils/homePlaceHelpers.js`, `placeResultConverters.js`, `kakaoPlaceRecommendation.js`, `aiWebSearchPolicy.js`; `frontend/vite.config.js`의 공유 TypeScript 파일 해석.
- 오류/제보 화면: `frontend/src/views/MyPlaceReportsView.jsx`, `PlaceReportView.jsx`, `LoginView.jsx`, `InquiryCreateView.jsx`, `MyInquiryView.jsx`, `MypageView.jsx`, `BoardCreateView.jsx`, `BoardEditView.jsx`, `BoardDetailView.jsx`, `PreferenceSettingsView.jsx`, `SearchHistoryView.jsx`, `AdminOperationsView.jsx`, `AdminPlaceReportsView.jsx`.
- 검사: `frontend/src/views/HomeView.test.jsx`, `MapSearchView.test.jsx`, `frontend/src/hooks/useNotifications.test.jsx`, `frontend/src/utils/searchUx.test.js`, `frontend/src/api/recommendation.test.js`의 세션 오류 보존 검사. 웹 API 구현에는 다른 검색 작업의 변경이 함께 존재한다.

### 공통/사용자 응답

- `shared/search-ux.ts`, `shared/user-message.ts`.
- `backend/recommendations/serializers.py`, `views.py`, `test_mobile_admin_workflows.py`의 사용자 제보 공개 응답/접근제어 검사.

## 3. 뒤로 가기 상태 머신

모바일: 키보드 닫기 → 상세 WebView 내부 history → 상세 닫기 → expanded를 peek로 → peek를 collapsed로 → 이전 route/tab → history 없는 실제 홈 루트에서 종료 안내.

- 상세 Modal의 `onRequestClose`가 키보드·WebView history를 먼저 처리한다.
- focused 화면 처리기를 공통 뒤로 가기 처리에 등록한다. 탭은 history를 사용한다.
- 검색 상태 초기화는 뒤로 가기 처리에 포함하지 않는다.
- 웹: 같은 route의 상세/패널 history를 쌓는다. 브라우저 뒤로 가기는 상세 닫기 → expanded/peek/collapsed → 이전 route 순서다. Escape는 입력 focus 해제 → 상세 → 패널 순서로 처리한다. 웹에 앱 종료 안내는 표시하지 않는다.

## 4. 검색 패널 동작

| 단계 | 표시 |
|---|---|
| collapsed | 결과 수·간단 요약 |
| peek | 현재 선택 카드 한 개, 없으면 첫 카드 |
| expanded | 전체 리스트·더보기 |

단계 변경은 지도 위치·결과·선택 장소·canonical 조건을 수정하지 않는다. 모바일 버튼은 세 단계를 순환하고 웹 일반 검색은 단계 버튼을 제공한다. 웹 대화 검색은 접기/카드 보기/전체 보기 버튼을 제공한다. 로딩 중 기존 카드도 유지한다.

## 5. 마커와 카드 연결

서버 `place_key`가 있으면 우선 사용하고, 없으면 provider + external/place ID로 식별한다. 웹 표시용 변환 객체에도 원본 key를 저장한다. 웹 추천 카드 ID도 provider를 포함해 충돌을 방지한다.

마커 선택은 동일 장소를 선택하고 리스트를 펼쳐 해당 카드로 스크롤한다. 카드 선택은 선택 key를 지도에 전달해 마커를 강조하고 필요한 경우 중심을 옮긴다. 좌표 없는 후보도 리스트에 남기며 마커 번호는 원래 리스트 순서를 사용한다. 번호로 장소를 찾지 않는다.

## 6. 현재 조건·clarification·설명

서버 SearchPlan frame의 지역, 후보 업종, required/preferred features, 반경을 읽어서 chip을 만든다. 프론트에서 사용자 문장을 해석해 새 조건을 만들지 않는다.

chip은 읽기 전용이다. 조건 수정은 대화로 서버에 전달한 후 canonical 응답을 반영한다. 서버가 반환한 짧은 처리 설명을 대화에 표시한다.

clarification이 오면 이전 결과와 조건을 유지한다. 버튼의 label/value/action을 보존한다. 설명/비교 답변은 이전 리스트를 유지하고 서버의 referenced keys/results/indexes로 해당 카드 버튼과 highlight를 표시한다. 사용자 문장에서 순번을 다시 추론하지 않는다.

## 7. 오류 메시지 매핑

| 유형 | 사용자 표시 |
|---|---|
| 정상 검색 0건 | 조건에 맞는 장소를 찾지 못했어요. |
| 서버/공급자 장애 | 지금 장소 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요. |
| 위치 없음 | 현재 위치를 확인할 수 없어요. 위치 권한을 확인하거나 지역을 선택해 주세요. |
| 연결 실패 | 인터넷 연결을 확인하고 다시 시도해 주세요. |
| timeout | 응답이 늦어지고 있어요. 입력한 내용은 유지되니 다시 시도해 주세요. |
| 인증 만료 | 다시 로그인해 주세요. |
| 권한 없음 | 이 정보를 확인하거나 변경할 권한이 없어요. |
| 충돌 | 처리 상태가 바뀌었어요. 같은 내용으로 다시 시도해 주세요. |
| 요청 제한 | 요청이 잠시 몰리고 있어요. 잠시 후 다시 시도해 주세요. |
| 잘못된 입력 | 안전한 한국어 validation 안내 또는 입력 내용을 확인해 주세요. |

모바일/웹 소스에서 사용자 오류 표시를 검색했다. 숫자 상태 코드, raw exception, stack, 환경변수명, enum, API/개발자 영어는 공통 표시 필터로 차단한다. 로그인·회원가입·제보·저장·게시판·문의·설정 등 직접 오류 표시 경로도 정리했다. 장애를 빈 검색으로 표시하지 않는다. 신규 오류 로그는 status/kind만 기록해 요청 header/body/인증값이 포함되지 않게 했다. AI Web Search의 실행 의미는 바꾸지 않고 사용자 문구·debug 표시만 정리했다.

## 8. unread 처리

unread count는 실제 응답 중 읽지 않았고 설정상 표시 가능한 알림 수다. 0건이면 점을 렌더하지 않는다. 모두 읽음 처리는 서버 갱신/재조회와 연결한다.

로그아웃과 계정 전환 때 이전 계정 목록을 즉시 숨긴다. 이전 계정의 늦은 응답은 request revision/account guard로 버린다. 웹은 설정 변경 즉시 재계산하고, 모바일은 설정 화면에서 돌아오는 focus/reload 때 저장 설정을 다시 읽는다.

## 9. 제보 내부 정보

일반 사용자 목록·상세·접수 응답에서 user/reviewer ID·username, 내부 메모, client_request_id, 내부 status/report_type 코드와 place FK를 제외했다. 사용자에게 장소명, 접수일, 한국어 상태/유형, 작성 내용, 처리 결과를 제공한다. 처리 결과는 공개 안내 문구이며 내부 검토 메모를 재사용하지 않는다.

report ID는 상세 route/요청 식별에만 남고 사용자에게 접수번호처럼 표시하지 않는다. 관리자 응답은 별도의 관리자 serializer를 사용한다. ID 숨김과 별개로 타 사용자 제보 상세 404 및 목록 owner 필터를 자동 검사했다.

## 10. 검증과 남아 있는 UI 검증

| 검사 | 결과 |
|---|---|
| 웹 전체 Vitest | 113건 통과 |
| 웹 production build | 통과; 기존 큰 bundle 경고 있음 |
| 모바일 화면/알림 Vitest | 9건 통과 |
| 모바일 연결 오류 Node 검사 | 6건 통과 |
| 모바일 TypeScript / lint | 통과, lint 오류·경고 0 |
| 사용자 제보 Django 격리 검사 | 4건 통과, system check 통과 |

웹: 실제 React 화면에서 검색/clarification/action, 기존 결과·조건 유지, 비교 카드 연결, 오류/동일 재시도, 새 대화 후 늦은 응답, 상세→브라우저 뒤로→패널 단계/결과 유지, 알림 계정·설정 lifecycle를 검사했다.

모바일: 실제 추천 React 화면을 native 어댑터로 실행해 검색→상세→닫기, clarification/action, 마커→카드 스크롤→카드 선택→지도 선택, 오류/동일 세션 재시도, 새 대화 후 늦은 응답, 공통 뒤로 가기 우선순위, unread lifecycle를 검사했다.

실기기의 소프트 키보드·Android 하드웨어 뒤로 가기·외부 WebView history·지도 SDK 실제 터치와 여러 화면 크기의 시각 QA는 아직 수동 확인하지 않았다. 자동 검사에서 해당 SDK/OS는 어댑터 또는 mock을 사용했다. 조건 chip 직접 편집은 제공하지 않는다. 일부 카테고리는 사진 대신 대표 아이콘이다. 웹 상세 iframe 내부 history는 브라우저가 처리하며 cross-origin history를 프론트가 재구현하지 않는다.

운영 배포·새 모바일 바이너리 설치는 실행하지 않았다. 이번 결과는 로컬 코드와 자동 검증 완료다.

### 재현 명령

- 웹: `cd frontend; npm test -- --silent; npm run build`
- 모바일: `cd mobile; npm run test:ux; npm test; npx tsc --noEmit; npm run lint` (`frontend/node_modules`의 기존 테스트 도구를 재사용)
- Django: `backend/venv/Scripts/python.exe manage.py test recommendations.test_mobile_admin_workflows.MobileAdminWorkflowTests.test_report_detail_is_owner_only_and_includes_description recommendations.test_mobile_admin_workflows.MobileAdminWorkflowTests.test_user_report_list_filters_status_without_exposing_other_users recommendations.test_mobile_admin_workflows.MobileAdminWorkflowTests.test_report_accepts_device_coordinates_with_more_than_six_decimals recommendations.test_mobile_admin_workflows.MobileAdminWorkflowTests.test_report_retry_replays_the_same_receipt_without_duplicate_images_or_rows --settings=config.test_settings --noinput` (backend에서 실행)
