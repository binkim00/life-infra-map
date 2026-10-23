# 앱 잔여 검증·근거 수집 점검 — 2026-10-15 15:17 KST

운영 DB는 REPEATABLE READ READ ONLY, SQL timeout 5초로 집계했다. 서비스·설정·데이터·Git index 변경은 없다.

- 수집 worker/scheduler와 기존 서비스 실행 중. health 보유 5개 정상.
- cycle_date별 완료: 10/14 3000작업, 10/15 3000작업. 달력일 처리량과 다르다.
- 최근 완료 500작업(10/15 13:10~15:10 KST): 요청989, 신규근거31, 근거 있는 작업20(4%). miss: IDENTITY_MISMATCH275, NO_TAG_EXPRESSION182, NO_SEARCH_RESULT23, none20. AI호출0.
- 최근24시간(10/14 15:17~10/15 15:17 KST) 생성 Evidence258: naver_blog_search253/web_search5. pending256/rejected2. 생성 시 이미 만료0/현재 만료0/유효 긍정 approved0. 신규 PlaceTag0. 기존 PlaceTag 갱신·전환 수는 이번 집계로 측정하지 않았다. job표본과 Evidence24h는 모집단이 달라 직접 나누지 않는다.
- 최근24h review reason: different_address_needs_branch_or_move_check216, place_identity_not_explicit_in_title_and_quote26, requires_human_context_review9, explicit_opposite_statement2, tag_not_directly_attributed_to_place5. 원문/장소/주소/URL 미출력.
- 네이버 API 달력일 사용: 10/14 6362요청/성공6362, 10/15 6593/6593, 실패·rate_limited 각각0. 성공 응답이 유효 근거 생성은 아니다.
- 결론: 수집과 신선도는 관찰 범위에서 작동하나 장소 귀속/승인 병목으로 신규 사용 가능 근거가 늘었다는 증거는 없다. 보류216건은 검토 사유이며 실제로 전부 다른 지점이라고 확정하지 않는다.
- 앱은 MOBILE_PLAY_WARNINGS_2026-10-14 최신 기록 기준 code7 업로드·심사 제출, Android16 주요 화면 검증. 실제 Play code7 제공/경고 재분석·새 OAuth 전체·사진 제보 제출 전체·하위 Android/태블릿 검증은 남음. 이번에는 새 앱 실행/콘솔 확인 없이 기존 증거만 검토했다. 새 확정 결함은 발견하지 않았지만 결함 없음 증명도 아니다.

다음 한 가지 행동: 보류 중 주소·지점 귀속 사례의 제한된 표본을 읽기 전용으로 대조해 실제 다른 지점과 판정 과잉을 구분한다. 자동 승인 완화나 운영 수정은 하지 않는다.
