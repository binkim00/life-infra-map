# CPU 대응 후 수집 품질 분석 — 2026-10-13

## 결론

CPU 안정과 수집 품질은 별개다. 10월 12~13일 계획 작업 중 09:15 KST 현재 completed 6,480건에서 Evidence를 얻은 작업은 392건(6.05%)이다. 장소 귀속 실패가 4,859건(74.98%)으로 가장 크다. 같은 기간 생성된 네이버 Evidence 688건 중 639건(92.88%)은 조회 시점에 만료되어 있고, 현재 유효한 긍정 승인 근거는 0건이다. 신규 PlaceTag는 확인 필요 2건이고 신규 verified 행은 0건이다. 기존 행의 상태 전환 수는 이력 부족으로 확정할 수 없다.

하루 6,000은 Evidence 생성·승인·완료 보장치가 아니라 **일일 계획 장소 작업 상한**이다. 12일 계획은 4,475건(74.58%), 완료는 4,398건(73.30%)이다. 완료 부족분 1,602건은 미계획 1,525건과 대기 77건으로 분해된다. 13일은 09:15까지의 부분 기간이므로 하루 목표 미달로 확정하지 않는다.

## 범위·조회와 증거 경계

- 대상: backend 수집·Evidence. 검색 로직/UI/운영 설정/데이터/마이그레이션은 변경하지 않았다. 현재 checkout은 codex/disk-maintenance이며 기존 tracked/untracked 변경을 보존했다.
- AWS 서울 리전 i-08cbd0f853d69ed38에서 SSM으로 실제 worker의 코드·비밀값을 제외한 설정과 DB 집계만 읽었다. SQL은 READ ONLY transaction, statement_timeout 15초, lock_timeout 2초(주 집계), 날짜 제한을 사용했다. 모델의 provider/cycle/status, created_at 인덱스와 migration 0021 정의를 확인했다. 실행 계획 자체를 수집하지 않았으므로 모든 쿼리의 인덱스 사용을 보증하지 않는다.
- 주 집계 기준 시각: **2026-10-13 09:15:00.686678 KST**. jobs는 cycle_date 12~13일, Evidence/신규 PlaceTag는 created_at [12일 00:00 KST, 기준 시각)이다. 보조 집계는 같은 cutoff를 사용하되 후속 조회의 현재 검토 상태를 읽었으므로 하나의 장기 snapshot이 아니다.
- 표본은 사유별 최초 완료 작업 1개씩 5개이며 이름·주소·URL·인용문·개인정보·원문 로그는 내보내지 않았다. 분포 추정에는 전체 기간 집계만 사용했다.
- SSM 확인 ID: 주 집계 c80147f7-9a39-4062-ae5a-e98749fb5452, 보조 집계 150e10e6-1026-4278-9b16-ccc872446c3c. 두 실행 Success. 코드 보조 읽기 ea7d50ea-2e71-4267-b877-ba69c2da6e5d는 마지막 설정 이름 오타로 Failed였고, 올바른 TAG_COLLECTION_QUEUE_HIGH/LOW를 보조 집계에서 재확인했다. 이 실패는 수집 worker 실패가 아니다.
- CPU·revision·경보는 docs/CODEX_STATE.md의 **09:05 이전 직접 조회 기록**을 참조했다. 본 분석에서 CloudWatch를 재조회하지 않았다. 기록상 revision 76e2de2f9b30ad096022197dd946138d2a52668f, 10월 11일 04:25:52~58 KST 배포, 경보 4개 OK, 12일 CPU 평균 6.11%/최고 5분 평균 31.68%/표본 Maximum 최고 77.73%. 경보 OK 복귀가 배포보다 이르므로 모든 과거 경보를 동일 원인으로 묶거나 수정의 인과적 감소율을 주장하지 않는다.
- 로컬에는 docs/operations/collection-resource-budget.md가 없어 초기 문구를 현재 배포 상태로 사용하지 않았다. 운영 bounded planner/worker pacing True는 이번 실제 설정 조회에서도 확인했다.

## 통계와 판정 코드

2026-10-13 P0 구현 중 고정 CPU revision 원본을 재대조해 정의를 정정했다. 운영 quota는 예약일에 요청을 귀속하고 실제 요청 수를 planned_requests로 절단하지 않는다. 아래 초기 분석의 정산일·요청 상한 설명은 이전 로컬 코드와 혼동한 것이다. 476건 차이는 계획일과 quota 예약 usage_date의 차이이며, 그 숫자만으로 자정 이후 실행한 요청 수를 확정할 수 없다. 집계 수치·완료 일자 분해·품질 결론은 유지한다. [P0 구현 보고서](COLLECTION_TELEMETRY_P0_2026-10-13.md)에 로컬/CPU 기반과 날짜 정책을 구분했다.

실제 운영 코드의 process_place_tag_collection_jobs.process_jobs는 error가 빈 문자열 또는 insufficient_evidence면 completed로 종료한다. quota success_count에도 insufficient_evidence 요청을 성공으로 정산한다. 따라서 completed와 success_count는 품질 성공 지표가 아니다.

place_tag_collection.collect_naver_place_evidence의 분기는 추출 후보 리스트가 비었을 때만 insufficient_evidence를 반환한다. 순서대로 검색 결과 0 → NO_SEARCH_RESULT, identity match 0 → IDENTITY_MISMATCH, 매칭 결과가 모두 60자 미만 → INSUFFICIENT_SNIPPET, tag_expressions 0 → NO_TAG_EXPRESSION, 기타 → OTHER다. 이는 서로 배타적인 **작업 종료 우선순위 사유**이며 결과별 거절 사유와 분모가 다르다.

polarity_assessment는 직접/보조 긍정 표현, 반대 표현, 약한 표현을 구분한다. 긍정과 부정 동시 존재 또는 문맥 제외는 unknown, 부정만 있으면 negative/CONTRADICTING, 직접 긍정은 DIRECT, 보조 긍정은 SUPPORTING이다. unknown과 같은 (tag, URL, polarity)의 반복은 추출 리스트에서 제외한다. 후속 save_place_candidate_evidence는 canonical URL 기준 기존 같은 장소·태그·극성 근거를 재사용하고 만료를 연장하지 않는다.

- stats.evidences: collector 반환 후보 수. 부정·만료·미승인·기존 재사용도 포함할 수 있다.
- new_evidences: DB에서 실제 새로 생성한 수.
- active_evidences/new_active_evidences: 저장 당시 expires_at 검사만 한다. 승인/긍정 검사가 아니며 시간이 지난 뒤 현재 유효 수와 달라질 수 있다.
- stats는 마지막 처리 결과이고 별도 실행 이력 원장이 아니다. requests는 planned_requests 상한으로 정산된다.
- 현재 승인 허용: review 없음 또는 approved, 동시에 expires_at NULL 또는 현재보다 미래. approved_limited/pending/rejected/research는 제외. 본 기간에는 review 없는 신규 근거가 없었다.
- PlaceTag confirmed는 공식 긍정 근거, 또는 관리자/사용자 검증과 독립 웹 근거 등의 조건이 필요하다. 웹 긍정 2개 이상은 candidate일 수 있으며 자동 콘텐츠 승인만으로 현장 검증을 대신하지 않는다. 실제 운영 save와 review 함수의 조건을 확인했다. 로컬 aggregate 코드에는 다른 채팅 변경이 있어 이번에 실행하지 않았다.
- report_daily_collection은 jobs를 cycle_date, Evidence와 태그를 created_at으로 묶고 승인·현재 유효성은 세지 않는다. scheduler useful_completed는 completed-insufficient로, 일보 useful_jobs(stats.evidences>0)와 정의가 다르다.

## 일별 작업·요청 수와 날짜 경계

| 계획일 | 계획 | completed | queued | 근거 있는 작업 | 반환/신규 Evidence | 저장 당시 active | stats 요청 | 달력일 quota 요청 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-12 | 4475 | 4398 | 77 | 184 | 288/288 | 21 | 8737 | 8261 |
| 2026-10-13 | 2352 | 2082 | 270 | 208 | 400/400 | 28 | 4351 | 4827 |

양일 retry/failed/processing/미정산 checkpoint는 0이다. 공급자는 jobs 모두 naver_search다. 12일 quota 8,261과 13일 4,827 모두 failed/rate_limited/reserved 0, daily_limit 25,000이다. 안전 예산은 90%=22,500으로 12일 사용률 36.72%이다. 할당량 소진이나 429가 관측된 미달 원인은 아니다.

12일 cycle completed 4,398건 중 실제 12일 완료는 4,167건, 13일 새벽 완료는 231건이다. 마지막 완료는 13일 01:12:48 KST다. 13일 cycle 첫 생성 00:14:53, 첫 완료 00:14:57이다. 12일 cycle stats 요청 8,737과 12일 quota 8,261의 차이 476은, 13일 quota 4,827과 13일 cycle stats 4,351의 차이와 일치한다. **계획일과 요청 정산일의 이월이 양일 합계 13,088에서 상쇄된다.** 다른 오래된 cycle의 달력일 처리 전체를 조회하지 않았으므로 위 완료 일자 표를 모든 작업의 일간 처리량으로 확대하지 않는다.

09:05 기록의 13일 completed 2,041/queued 211/요청 4,742 및 insufficient 6,057은 이전 표본이다. 09:15에는 completed 2,082/queued 270/요청 4,827, 양일 insufficient 6,088로 증가했다. 진행 중인 수집의 시각 차이를 오류로 해석하지 않는다.

## 단계별 수율과 실패 사유

| 단계 | 분자/분모 | 수율 또는 손실 |
| --- | --- | --- |
| Evidence 있는 완료 작업 | 392 / 6,480 | 6.05% |
| 귀속된 검색 결과 | 2,985 / 50,526 | 5.91% |
| 근거 후보가 있는 결과 | 651 / 2,985 귀속 결과 | 21.81% |
| 극성 확정 태그 추출 평가 | 721 / 36,757 평가 | 1.96% |
| 신규 네이버 Evidence | 688 / 6,480 완료 | 100작업당 10.62행; 다중 태그 가능 |
| 현재 유효 네이버 Evidence | 49 / 688 | 7.12% |
| 현재 유효 긍정 네이버 Evidence | 48 / 688 | 6.98% |
| 현재 유효 긍정 승인 네이버 Evidence | 0 / 688 | 0% |
| 새 verified PlaceTag | 0 / 신규 PlaceTag 2 | 0% |

| 작업 종료 | 건수 / completed 6,480 | 비율 |
| --- | --- | --- |
| IDENTITY_MISMATCH | 4859 | 74.98% |
| NO_TAG_EXPRESSION | 1045 | 16.13% |
| NO_SEARCH_RESULT | 180 | 2.78% |
| INSUFFICIENT_SNIPPET | 4 | 0.06% |
| Evidence 있음 | 392 | 6.05% |

검색 결과별 귀속 실패 47,541/50,526(94.09%), NO_FEATURE 2,128/2,985(71.29%), WEAK_FEATURE 206/2,985(6.90%). SOURCE_REJECT는 저장된 결과 거절 집계에서 0이다. direct: 결과 21,189/귀속 901/후보 결과 525, identity_discovery: 27,580/1,661/22, synonym: 1,757/423/104. query_stage별 반복 결과도 포함하므로 고유 글 성공률이 아니다. pack 이름은 실제 키와 최초 조회 투영이 달라 NULL이었으므로 pack별 수율을 만들어내지 않는다.

태그 평가 36,757개 중 unknown/UNKNOWN 35,770, unknown/WEAK 266, positive/DIRECT 666, positive/SUPPORTING 27, negative/CONTRADICTING 28이다. 판정 확정 721은 검색 시도별 추출 평가 수이고 저장 후보 688과 같을 필요가 없다. unknown 중 positive_terms가 있는 저장 평가 0건이지만 negative_terms·contextual_exclusion 세부 신호가 전부 저장되지는 않아 긍부정 충돌/문맥 제외의 정확한 개별 수는 산출 불가다.

## 지역·업종별 완료 수율

분모는 양일 **completed 작업**이다. 생성 장소·태그 수가 아니라 Evidence가 한 개 이상 반환된 작업 비율이다. 지역과 업종이 강하게 섞여 있으므로 지역 자체의 효과로 단정하지 않는다.

| 지역 | 완료 | 근거 있는 작업 | 수율 | 귀속 실패 | 태그 표현 부족 |
| --- | --- | --- | --- | --- | --- |
| 부산광역시 | 3480 | 356 | 10.23% | 2729 | 321 |
| 경기도 | 700 | 1 | 0.14% | 587 | 92 |
| 서울특별시 | 2000 | 32 | 1.60% | 1310 | 573 |
| 인천광역시 | 300 | 3 | 1.00% | 233 | 59 |

| 업종 | 완료 | 근거 있는 작업 | 수율 | 귀속 실패 | 태그 표현 부족 |
| --- | --- | --- | --- | --- | --- |
| restaurant | 3480 | 356 | 10.23% | 2729 | 321 |
| toilet | 1866 | 19 | 1.02% | 1492 | 312 |
| tourism | 1129 | 17 | 1.51% | 633 | 412 |
| city_park | 4 | 0 | 0.00% | 4 | 0 |
| parking | 1 | 0 | 0.00% | 1 | 0 |

cafe/library/beach/shelter는 이 기간 완료 표본 0으로 품질 평가 불가다. 13일 표본은 부산 restaurant에만 몰려 있다. 12일 계획 지역은 부산 1,475/3,000, 서울 2,000/2,000, 경기 700/700, 인천 300/300으로 부산 미계획 1,525건이 목표 차이와 정확히 일치한다. 다른 지역은 계획 목표 달성과 품질 성공을 구분해야 한다.

생성 Evidence 전체 699건=naver_blog_search 688 + web_search 11이다. web_search는 이 naver 작업 cohort의 성과로 귀속하지 않는다. 태그별 아래 수는 created_at 기간 전체 공급자 합계이고, 모두 현재 유효 긍정 승인 0이다.

| 생성 태그 상위 | 새 행 |
| --- | --- |
| 혼밥좋음 | 534 |
| 조용함 | 19 |
| 휠체어접근 | 19 |
| 데이트좋음 | 16 |
| 분위기좋음 | 16 |
| 대표메뉴뚜렷함 | 15 |
| 주차어려움 | 14 |
| 가성비좋음 | 10 |
| 소음큼 | 7 |
| 전망좋음 | 6 |
| 장애인시설 | 6 |
| 혼잡함 | 5 |
| 예약가능 | 5 |
| 웨이팅적음 | 4 |
| 메뉴선택폭넓음 | 4 |

혼밥좋음 534/699(76.39%) 편중이다. 이는 공급자·업종·수집 query/target 선택의 결과이며 전체 사용자 조건 coverage가 향상됐다는 뜻이 아니다.

## 만료·승인·중복·gate 손실

신규 네이버 688: positive 661, negative 27. 현재 유효 positive 48/negative 1, 만료 639. 저장 당시 active 합계 49와 현재 active 49가 이번 표본에서는 같다.

| 검토 상태/최근 기록 사유 | 네이버 건수 | 현재 active |
| --- | --- | --- |
| approved / exact_title_address_and_direct_tag_context | 2 | 0 |
| approved_limited / expired_pending_historical | 407 | 0 |
| pending / different_address_needs_branch_or_move_check | 196 | 37 |
| pending / place_identity_not_explicit_in_title_and_quote | 37 | 7 |
| pending / requires_human_context_review | 12 | 1 |
| pending / tag_not_directly_attributed_to_place | 13 | 4 |
| pending / tag_only_in_hashtag_or_unattributed | 4 | 0 |
| rejected / explicit_opposite_statement | 17 | 0 |

expired_pending_historical 407건은 저장된 검토 이력상 만료 과거 근거의 제한 승인이다. 이 사유가 현재 auto_review_content 함수의 단일 신규 분기라고 가정하지 않는다. approved 2건도 모두 만료다. 현재 유효 49건은 전부 pending이며, 그중 주소/이전·지점 확인 37, 제목·문장 귀속 7, 직접 태그 귀속 4, 사람 문맥 검토 1이다. web_search 11건도 모두 주소 확인 pending이다.

canonical 재사용은 이번 job stats에서 evidences=new_evidences=688이므로 저장 재사용 손실 0건이다. 검토 이력의 duplicate_original_preserved는 해당 생성 기간 0건이다. 검색 단계 반복 평가 제거까지 중복이 없었다는 뜻은 아니다.

새 PlaceTag는 web_evidence/needs_verification/is_verified=False 2건이다. 신규 Evidence와 같은 (place,tag)의 **현재** PlaceTag는 field_rule confirmed/verified 8, blog_search candidate 2, web_evidence needs_verification 8이다. field_rule 8은 기존 공식 근거일 수 있고, 생성 전후 상태 이력이 없으므로 이번 수집의 verified 전환으로 세지 않는다. 신규 verified 생성 0은 확인 가능하지만 기존 행의 정확한 candidate→confirmed 전환 수는 현재 테이블만으로 확정 불가다.

작은 대표 표본(사유별 최초 1건): 성공 results=5/matched=1/requests=1; 귀속 실패 5/0/2; 짧은 snippet 10/1/2(짧음 1); 결과 없음 0/0/2; 태그 표현 없음 10/1/2. 저장 결과를 요약한 표본이지 원문 현장 검증이나 잘못된 귀속을 판별한 gold set은 아니다.

## 6,000 미달: 확인 사실과 추론

운영에서 bounded planner=True, scan page=2,000, refill=100, wall budget=5초, cooldown=60초, queue low/high=250/500, worker batch=10, pacing=True, NAVER_RPS=5, safe API limit=22,500, revisit=90일, category max share=40%다.

**확인:** scheduler는 전체 queued/retry가 250 이상이면 그 tick의 신규 계획을 멈춘다. 한 번 최대 100건, 페이지 안에 있는 카테고리·지역 후보만 평가한다. 지역 목표와 당일 업종 최대 2,400건을 적용하고 90일 안의 queued/processing/completed/retry 장소를 제외한다. 예산·선택 상한으로 일부 후보가 빠지면 cursor를 유지한다. 제한으로 후보가 없으면 페이지를 넘길 수 있고 끝에서는 wrap한다. 가장 최근 planner는 scanned 2,000/candidates 300/planned 100/1,029ms/deferred=False, covered_strata 1이다. 최신 한 번의 성공으로 하루 전체 계획기가 순조로웠다고 주장하지 않는다.

**확인:** 6,000 pacing 간격은 86,400/6,000=14.4초이다. 한 작업 실제 처리 시간이 이를 초과하면 추가 sleep은 없지만 초과 시간을 회수하지 않는다. 빈 큐/할당량 대기는 최대 60초 polling이다. 12일 cycle의 4,398건은 약 25시간 11분에 걸쳐 종료됐고, 단일 worker가 이틀 작업을 이월 처리했다. 13일 cycle도 첫 계획이 자정 약 15분 뒤다. 일간 목표와 이월 큐를 동시에 처리하면 당일 완료 보장은 어렵다.

**해석:** 당일 12일 cycle 완료 4,167은 하루 평균 약 20.74초/건에 해당한다(대기 포함; per-job duration이 아니다). 14.4초를 충분히 채우지 못한 처리/대기 손실이 존재한다. 그러나 duration, 빈 큐 시간, planner deferral 이유별 일간 누적 계측이 없어 처리 시간·탐색 제한·대기 각각의 기여 초/건은 확정할 수 없다. 부산 후보 탐색과 지역/업종 편중이 개선 후보이며, 특정 cap 하나가 1,525건 전부를 설명한다고 단정하지 않는다. 13일 restaurant 계획 2,352는 업종 cap 2,400에 가까워 이후 다른 업종 후보 발굴이 필요하다는 전망이다.

계획 상한 자체는 100건/분 기준 하루 최대 144,000건으로 명목 6,000보다 충분하지만, 실제는 큐·후보·예산·시간·지역/업종 상한을 함께 적용하므로 명목 refill만 올리는 것은 해결 근거가 없다. 12일 API 소진·rate limit·retry·checkpoint 누적은 관측되지 않았다. CPU 안정 상태와 낮은 유효 수율을 별도로 판단한다.

## 개선 우선순위와 안전한 검증안

이번에는 분석과 제안만 완료했다. 운영 수집 강도, TTL, 승인 기준, DB를 변경하지 않았다.

| 우선순위 | 구체적 수정 후보 | 예상 영향과 한계 | 관련 검증 |
| --- | --- | --- | --- |
| P0 | process_jobs/report_daily_collection에 cycle/달력일, 생성·유효·긍정·승인·verified를 각각 계수하고 bounded planner에 사유별 scanned/recent/category_cap/region_cap/budget/deadline/empty_queue 누적과 처리·sleep 시간 기록 | completed 성공 오해와 6,000 미달 기여도를 계측. 품질을 직접 올리는 수정은 아님 | test_daily_tag_collection에 자정 이월/insufficient success/부정·만료·pending 분리; 요청 합계 정산·checkpoint 재개 유지 |
| P1 | 수집 query/후보 선택에서 최신 관측일·직접 태그·지점 주소를 갖춘 근거 우선. 오래된 글은 historical 보조로 분리하고 저장 TTL 유지 | 만료 92.88%와 현재 pending 49건 병목을 겨냥. 최신 글 확보 가능량은 미측정이며 공급자 필터 지원부터 확인 필요 | 고정 입력 fixture로 최신/만료/관측일 없음, 재검색 시 만료 연장 금지; test_automatic_content_review 및 수집 provider tests |
| P1 | bounded_collection_planner에 지역·업종별 작은 순환 cursor/결핍 우선 탐색 후보를 설계. 유효 승인 수율 기준과 탐색 예산을 분리하고 기존 5초/2,000행 상한 유지 | 부산 계획 부족·restaurant/혼밥 편중 감소 후보. 현재 단일 cursor가 실제 부족을 얼마나 유발하는지는 계측 후 확인 | 고정 registry fixture로 한 업종 prefix/지역 cap/90일 재방문/cursor rollback/wrap/starvation; test_adaptive_budget, test_daily_tag_collection와 운영 revision resource tests |
| P2 | save/automatic_content_review에서 주소·지점 검토 대상으로 작은 내부 queue 만들고, 동명·지점·반대·해시태그·복수장소·정확한 도로번호 gold set으로 수집 귀속 판단 비교 | 최대 병목 귀속 74.98%와 active pending 주소 37건 개선 가능성 평가. 검토 gate를 단순 완화하지 않음 | test_automatic_content_review, test_naver_tag_evidence_provider, test_tag_evidence_aggregation; 잘못된 장소·긍정 귀속 증가 0을 우선 기준 |
| P2 | worker 목표를 계획 상한과 분리한 처리 예산 정책으로 설계. 예상 완료 시각/이월/빈 큐/장기 작업을 먼저 계측하고 CPU·쿼터 여유 내 옵션 비교 | 14.4초 pacing 초과·이월의 영향 평가. 현재 CPU 안정만으로 동시성/속도 증가 승인 근거가 되지 않음 | 가상 시계 테스트로 6,000 간격, 느린 작업, queue 대기, 일자 변경, heartbeat/정산 재개. 운영 강도 변경은 별도 승인·제한 검증 |

검증 순서: 네트워크·운영 DB 없는 합성 fixture에서 기존/수정 후보를 재생하고 → 사유별 작은 익명 gold set으로 귀속 precision·유효 긍정 승인/100요청·조건 조합 coverage를 비교하고 → 별도 승인된 제한 운영 평가에서 처리량/CPU 5분 평균·Maximum/쿼터/큐·오귀속을 함께 확인한다. 이번 문서 작업에는 코드 변경이 없어 애플리케이션 테스트를 실행하지 않았다. 분석 검증은 집계 합계/분모/날짜 이월/실제 코드 분기 대조로 완료했다.

## 남은 일과 다음 행동

일간 planner 손실의 정확한 기여도, per-job 처리·대기 시간, 실제 잘못된 귀속 비율, 기존 PlaceTag의 상태 전환 이력은 현재 자료로 확정할 수 없다. 최신 근거 원문 재확인·개선 구현·운영 적용도 미실행이다.

**다음 한 가지 행동:** 별도 로컬 작업에서 P0 수집 단계·시간·날짜 경계 계측을 구현하고 자정 이월 및 만료/승인 분리 테스트로 검증한다.
