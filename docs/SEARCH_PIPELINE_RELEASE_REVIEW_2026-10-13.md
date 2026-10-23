# 검색 파이프라인 제한 배포 검토 — 2026-10-13

> 최신 판단: [서울 선택 SQL tail 진단](SEARCH_SEOUL_SQL_TAIL_REVIEW_2026-10-13.md). bounded selection의 heap I/O 병목 증거 확보. v7 결과 회귀/v8 성능 회귀로 통합·배포 대상에서 제외하고 v6 유지. covering index 격리 검증 초안만 준비했으며 운영 index/migration/data/서비스 변경과 실제 tail 해결은 미완료다.

> 최신 판단: [v6 공통 근거 계산 재사용 검증](SEARCH_PREPARED_EVIDENCE_REVIEW_2026-10-13.md).93개 회귀·12개×5회 비교에서 실패/결과·프로필 불일치/조건 위반0, 전체median508.39→244.30ms,12개median 모두 개선. 단, 서울1 선택/상세 SQL의 단발4.82초와 운영 이미지 확인/승인은 남아 있어 운영 배포 완료로 취급하지 않는다.

> 최신 판단: [상세 조회 통합·5회 반복 검토](SEARCH_HYDRATION_REPEAT_REVIEW_2026-10-13.md). 최종 v5의90개 회귀·60 paired cases에서 결과/프로필 동일, SQL수 중앙값13→10회. 전체509→535ms와 서울4종 지연 기준 초과로 운영 성능 승인/배포 보류이며 프로필 대체 실험은 제외했다.

> 최신 판단: [검색 A v3 재검증](SEARCH_PACKAGE_A_REVALIDATION_2026-10-13.md). 추가 근거 query를 per-tag 집합 교집합으로 개선해 비용10종 모두 완료, 조건 위반0의12개 전후 비교와90개 회귀를 확보했다. 기존 코드 서울1의 첫 SQL timeout은 표적 재검사로 완료. 추가 query 실행 합계0.780~52.240ms이나 전체 retrieval 지연이 늘어난 사례가 있어 운영 성능 승인/배포는 보류다.

> 후속 검증: [두 기능 선별 패키지·격리 회귀·PostgreSQL 비용](SEARCH_PACKAGE_A_VALIDATION_2026-10-13.md). 후보 추가 조회의 축약 누락을 보완한 패키지와 rollback을 작성했고 격리 89개 검사 통과. 추가 SQL 10종 중 9종 47.879~2,441.586ms 실측, 서울4 OperationalError로 성능 수용 보류. 운영 최종 결과 12개 paired 비교는 5초 SQL 제한으로 중단되어 미완료다. 아래 기록은 앞선 리뷰 단계이며 최신 승인 판단은 후속 검증의 배포 보류를 따른다.

## 판단과 증거 범위

**준비안 작성 완료, 운영 배포 보류.** 기존 배포분과 로컬 후속 변경을 분리했다. identity 조회의 로컬 결함 2종을 수정했고 SQLite 관련 검사 102개가 통과했다. 운영 Django 파일 해시·실제 설정과 12개 통제 검색을 읽기 전용으로 확인했다. AI 공급자 파일럿 성과·추가 지연·Top-K 순증은 미측정이다.

이 보고서는 backend 검색·추천 담당 범위다. 수집 planner/worker, 운영 데이터/마이그레이션, UI/mobile, 공용 Git 통합은 변경하지 않았다. checkout은 `codex/disk-maintenance`, 확인 HEAD는 `6f1f8323cc87e3def055905a69e44c3af8322221`. 기존 tracked/untracked 변경은 보존했고 commit/push/브랜치 전환을 하지 않았다. 다른 동시 채팅에 연락하지 않았다.

10월 6일 보고서는 과거 기록이다. 이번 운영 해시 확인은 SSM 읽기 전용 명령으로 Django 컨테이너 안의 파일을 직접 읽었다. 컨테이너 image revision은 파일 단위 선별 배포 전체를 증명하지 않으므로 배포 여부는 아래 파일 hash로 판단했다. provider 키 값은 읽거나 출력하지 않았다.

## 1. 운영과 로컬, 다른 브랜치 분리

경로 접두사는 `backend/recommendations/services/`. 로컬 exact hash·로컬/원격 추적 ref 비교는 [파일 비교](../runtime/search-pipeline-file-comparison-20261013.json)에 있다. 원격 fetch는 실행하지 않았으므로 origin ref는 현재 로컬에 저장된 snapshot이다.

| 파일 | 현재 운영 SHA-256 / 상태 | 판단 |
| --- | --- | --- |
| ai_intent_planner.py | 2ed7a0d0b1102ade86d81b53d593b605edb5f82d5ecec497e40ee28d0aeeedb6 | 현재 로컬과 일치. Git dirty여도 미배포로 분류하면 안 됨 |
| search_hard_gate.py | b71c81647ab72db22d09a7e55283fa1b1ffcb93e468c621d5eea755c5f87b651 | 현재 로컬과 일치, 기존 배포분 |
| kakao_local.py | 85ef04253a8d04287cb7b3826ebea9db641039055d4d7a20e1309eb9244f3b24 | 현재 로컬과 일치, 기존 배포분 |
| ai_search_orchestrator.py | cc265e7968bfc8e1d2bfb689acd1ed257fc2c9095335ca8eaf005d0e1ad1972d | 10월 6일 backend-final-v2 꾸러미와 exact 일치, 현재 로컬과 다름 |
| tag_evidence_aggregation.py | 049e629d18ad0f2a31faa10b5d9065fe5bbc96b561baa0f658264c9b0e7c1b77 | 로컬 독립성 변경 미반영 |
| ai_web_search_provider.py | cfff8a5c8f7de160c391ee93c302f82bbb25e5d1b306930e994dd8cb84ff8996 | 로컬 파일럿 변경 미반영 |
| external_place_identity.py | 파일 없음 | 로컬 신규, 이번 안전 수정 포함 |
| search_candidate_trace.py / search_pipeline_metrics.py | 파일 없음 | 로컬 신규 |

검색 파일 9개의 LF 정규화 내용은 조사한 모든 로컬 branch·origin 추적 ref의 해당 파일 전체 내용과 불일치했다. 이는 **파일 전체가 동일한 ref 없음**을 의미한다. 다른 ref의 부분 hunk/patch 중복·동등 구현이 없다는 증거는 아니다. 특히 이미 배포된 dirty 3개를 다시 미배포 목록에 넣으면 중복 반영된다. 공용 Git 통합 담당은 새 remote 상태 및 부분 patch 동등성을 추가 확인해야 한다.

운영 일치 꾸러미를 기준으로 만든 [orchestrator 후속 차이](../runtime/search-pipeline-orchestrator-delta-20261013.patch)는 HEAD diff와 구분한다. raw Evidence 추가 조회, identity 조인·병합 제한, gate 근거 fallback, sparse web, trace/metrics가 주요 후속 hunk다.

배포 단위 제안:

- A: orchestrator의 원시 근거 후보 추가 조회와 reranker 비활성 fallback hunk만 선별. AI 가중치는 유지. 기존 intent/gate/Kakao 파일은 hash 보존.
- B: A 이후 identity 모듈·연결/병합 hunk + config의 `EXTERNAL_PLACE_IDENTITY_ENABLED` 정의. trace/metrics는 별도 관측 hunk와 두 모듈·설정 정의를 함께 포함해야 import 실패가 없다.
- C: Evidence 독립성 aggregation 변경. 이 함수는 수집/승격도 호출하므로 검색 전용 변경으로 함께 배포하지 말고 수집 담당의 영향 검토 필요.
- D: ai_web_search_provider + sparse web hunk·설정. 비용·지연 상한 보강 전 운영 활성화 보류.

`backend/config/settings.py`는 혼합 변경이므로 전체 복사하지 않고 위 기능 플래그 hunk만 검토한다. views/serializers/conversation 파일의 다른 업무 변경, bootstrap_priority/search_coverage_demand, 수집 command와 테스트, deploy/gateway, frontend/mobile/shared는 이 패키지에서 제외한다. 현재 working tree 전체를 일괄 배포하는 manifest는 만들지 않았다.

## 2. 검색 코드 리뷰와 로컬 수정

| 항목 | 확인 및 판단 |
| --- | --- |
| 첫 후보 창 밖의 근거 장소 | `_evidenced_required_place_ids`가 모든 필수 태그의 유효·양성·검토 허용 Evidence 조합을 추가 조회한다. 태그명 exact 조합이므로 alias/UNKNOWN·충돌은 최종 gate가 다시 판정해야 한다. PostgreSQL 공간 조회 성능은 이번 로컬 SQLite 검사로 검증되지 않음 |
| AI reranker 비활성 fallback | `_grounded_internal_fallback`은 internal Place + 현재 gate 통과 + active Evidence를 요구한다. 직접 업종/대상 근거와 필수조건 정책을 적용하며 임의 미확인 top-up을 하지 않는다 |
| 외부 identity | 전체 이름+주소/가까운 좌표, 주소/좌표 충돌 차단, 명시적 조인 이전에는 Evidence를 물려주지 않는 설계. **이번 수정:** NaN/무한/범위 밖/한쪽만 있는 좌표를 direct ID 조회 이전에 차단; nearby 101건 조회로 100건 창 포화 시 `ambiguous` 처리. 외부 ID가 일치하고 정체성도 일치한 직접 조회는 우선한다 |
| Evidence join | internal Place를 확정한 후보만 기존 Evidence 연결. source facts, inferred tag, matched explanation을 별도 필드로 유지. `verified_tags` 수와 `hard_gate_active_tags` 수는 의미가 다름 |
| 독립성 | aggregation은 동일 게시자/정규화 인용문을 중복 계산하지 않는다. **한계:** gate의 semantic_quote_fallback은 서로 다른 URL 2개 기준이며 aggregation의 게시자/인용문 독립성과 동일하지 않다. 일반 웹 추출도 정책상 trusted로 처리될 수 있다. 따라서 '독립 근거가 확인된 결과'라는 새 보장은 현재 코드로 주장할 수 없음 |
| 필수조건 / 부족 결과 | 모든 활성 필수조건을 결과 정책에서 다시 확인. UNKNOWN·부분 충족은 기본 조건 충족 결과로 채우지 않는다. 명시적인 미확인 보기만 별도 정책. 근거 부족 0건과 공급자 실패를 구분해야 함 |
| trace 개인정보 | 랜덤 요청 salt로 candidate key 해시, 원문/장소명/주소/외부 ID/인용문 제외, 사유 enum 허용 목록. 익명에 가까운 요청 내 진단이지 장기 장소별 추적 키가 아님. logger warning으로 남으므로 내부 접근·보존 기간·샘플링 승인 필요 |
| trace/metrics 정확성 | trace는 병합 alias별 행에 join을 표시해 한 장소가 두 행으로 집계될 수 있다. semantic 입력은 trace 인터페이스에 없음. metrics의 evidence_join_success는 gate 이후만 세므로 전체 join 성공률이 아님. ranking 앞 shortlist/required policy 손실과 identity·join 시간도 분리 계측되지 않음. 이 값으로 완전한 funnel 실패율을 계산하면 안 됨 |
| AI 비용·지연 | sparse는 0~1개 발동, 2개는 명시적 확장, 3개 이상 생략, 쿼리 1개·후보 3개·출력 800 tokens 한도, 10분/100개 process cache. 그러나 서버오류 재시도 1회로 **provider HTTP 최대 2회**일 수 있고 timeout은 회당 AI_REQUEST_TIMEOUT(기본20초). 전역 일일 비용/동시성 cap·전체 deadline·circuit breaker 없음. 공급자 예외 stack의 URL/본문 노출 경로도 별도 점검 필요 |

실시간 웹 결과는 발견 후보이며 그 자체가 장소 속성의 사실 증거가 아니다. identity+기존 유효 Evidence+전체 gate를 통과해야 확인 결과에 포함된다.

이번 변경 파일은 `external_place_identity.py`, `test_external_place_identity.py` 두 개다. 관련 25개 선행 검사 통과 후 추가 회귀·대화 flow 포함 **102 tests / failures 0 / errors 0**, Django system check 0 issues. 첫 추가 검사에서는 테스트 fixture의 unique external ID 누락을 수정 후 재검사했다. 10월 6일 1,004개 검사는 과거 기록이며 이번 전체 suite 통과로 표현하지 않는다.

## 3. 기존 12개 검색 복원과 운영 baseline

10월 6일 완료 보고서에서 부산/서울 × 6조건, 반경 5km, DB 후보30·Kakao45, Top5라는 **시나리오 종류와 수집 한도**를 복원했다. 당시 보고서에는 원문 입력/정확한 좌표가 보존돼 있지 않아 byte 단위 동일 요청 복원은 불가능하다. 이번부터 다음 protocol을 고정한다. 부산 중심 (35.1796,129.0756), 서울 중심 (37.5665,126.9780)은 재현용 명시 좌표이며 도시 전체 검색이 아니다.

고정 입력 query/normalized query/primary search query는 `카페`. frame: candidate_category_codes=[cafe], candidate_place_types/target_objects=[카페], required_features=아래 조건, preferred_features=[], radius_m=5000. lat/lng는 위 도시 좌표, radius=5000, limit=5. natural-language planner는 고정 frame으로 우회한다. **자연어 intent 정확도나 공개 HTTP E2E 평가가 아니다.**

운영 Django 코드·운영 DB를 사용한 읽기 전용 내부 호출이다. PostgreSQL `SET TRANSACTION READ ONLY` + 마지막 rollback으로 공유 DB 변경을 막았다. DB/Kakao 후보를 한 번 수집한 뒤 같은 후보를 _run_ai_search에 전달해 최종 반환까지 관측했다. AI 설정은 변경하지 않았고 provider 호출은 비활성. Kakao 읽기 조회는 외부 쿼터를 소비한다. 첫 probe는 primary_search_queries 누락으로 clarification이 발생해 무효 처리하고, 이를 보완한 v2만 아래 baseline으로 채택했다.

[고정 측정 코드](../runtime/search-pipeline-baseline-20261013.py), [집계 결과](../runtime/search-pipeline-baseline-20261013.json). 모든 행 DB30/Kakao45, action=search다. 'join'은 gate 진단에 기록된 활성 태그가 **하나라도 있는 후보 수**이며 모든 조건 충족 수가 아니다. linked는 병합 후 internal Place가 있는 후보 수로 strict identity lookup 성공 건수가 아니다.

| ID | 필수조건 | 병합후 | linked | join | gate통과/탈락 | 최종/조건확인 | 위반 | 측정초 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 부산-1 | 없음 | 58 | 25 | 12 | 57/1 | 5/5 | 0 | 3.687 |
| 부산-2 | 조용함 | 65 | 28 | 19 | 9/56 | 0/0 | 0 | 1.519 |
| 부산-3 | 콘센트있음 | 66 | 28 | 22 | 13/53 | 0/0 | 0 | 1.075 |
| 부산-4 | 조용함+콘센트있음 | 70 | 30 | 25 | 4/66 | 0/0 | 0 | 1.054 |
| 부산-5 | 조용함+콘센트있음+노트북작업 | 72 | 29 | 28 | 4/68 | 0/0 | 0 | 1.162 |
| 부산-6 | 혼자이용좋음+장기체류좋음 | 59 | 26 | 13 | 0/59 | 0/0 | 0 | 0.894 |
| 서울-1 | 없음 | 63 | 28 | 15 | 60/3 | 5/5 | 0 | 6.110 |
| 서울-2 | 조용함 | 63 | 28 | 15 | 0/63 | 0/0 | 0 | 0.948 |
| 서울-3 | 콘센트있음 | 63 | 28 | 15 | 0/63 | 0/0 | 0 | 0.721 |
| 서울-4 | 조용함+콘센트있음 | 63 | 28 | 15 | 0/63 | 0/0 | 0 | 0.856 |
| 서울-5 | 조용함+콘센트있음+노트북작업 | 63 | 28 | 17 | 0/63 | 0/0 | 0 | 0.952 |
| 서울-6 | 혼자이용좋음+장기체류좋음 | 63 | 28 | 15 | 0/63 | 0/0 | 0 | 0.715 |

단계 손실 해석:

- retrieval75→병합후58~72는 중복/기존 병합 영향으로 '유효 장소 손실'이라고 단정할 수 없다. identity 전용 모듈은 운영에 없어 strict match/ambiguous 분류는 미계측.
- join은 gate 통과/탈락 후보의 active tag 존재를 읽었다. 모든 필수조건 조합/독립 출처 충족 실패를 별도 카운터로 측정하지 못했다.
- 부산 2~5의 gate→최종 손실은 각각 9→0, 13→0, 4→0, 4→0. ranking shortlist→ranking→최종 정책별 실제 개별 손실은 trace가 없어 N/A다. 로컬 fallback 개선이 이를 회복한다는 설명은 **코드 근거 추정**, 운영 개선 실측 아님.
- 부산6·서울2~6은 gate 0이다. 근거 부족/후보 창/identity 미연결의 상대 기여율은 N/A. 부산/서울1은 최종5이며 대부분 상위 K 제한이지만 최종 필터까지 모두 같은 원인이라는 단정은 피한다.
- 조건 위반0은 반환 필드의 hard_gate_violations와 엄격 조건 행의 result_tier 검사다. 최종0인 행의 품질·false match 정밀도를 증명하지 않는다. 조건 없는 카페의 all_conditions_met도 조용함/콘센트 검증을 의미하지 않는다.
- 0.715~6.110초는 단일 회차 서버 측 후보 수집+통제 평가 시간이다. HTTP 지연·p95·AI 추가 지연이 아니다. 캐시/첫 조회 편차가 있으므로 평균 개선율을 내지 않는다.

10월 6일 gate/final은 부산 [58/5,15/0,14/2,5/1,4/1,0/0], 서울 [60/5,0/0,0/0,0/0,0/0,0/0]였다. 현재와 후보·Evidence가 변했고 좌표 원본도 미보존이므로 수치 차이를 배포 회귀 또는 개선 효과로 확정하지 않는다. 공개 홈/서면카페 HTTP200·30건 역시 별도 연결 증거다.

## 4. 동일 비교 기준과 승인 변경안

운영 현재 설정 직접 조회: AI_PROVIDER=rule, CONVERSATIONAL_SEARCH_AI_ENABLED=False, AI_RERANK_ENABLED=False, AI_WEB_SEARCH_ENABLED/AVAILABLE/AUTO_MERGE=False, SEMANTIC_RETRIEVAL_ENABLED/CANDIDATE_INJECTION=False. 새 sparse/identity/trace/metrics 설정은 현재 운영 settings에 속성이 없다(null); 로컬 정의는 모두 기본 False다. '운영 새 플래그가 설정되어 꺼짐'과 '아직 코드 자체가 없음'을 구분한다.

제한 배포는 A만 먼저 검토한다. raw retrieval/fallback은 별도 기능 플래그가 없으므로 flag off만으로 복구되지 않는다. B는 identity와 로그 관측을 분리 승인하며 새 플래그는 기본 False로 설치한다. C/D는 독립성 정책·비용 상한 검토 완료 전 제외한다.

승인 대상은 운영 일치 SHA를 base로 만든 A의 두 hunk, 필수 의존 import 목록, 최종 파일별 SHA, 백업/복구 경로, 적용 Django 컨테이너 하나와 재시작 여부를 명시한 **선별 패키지**여야 한다. 현재 full orchestrator를 복사하면 B/D/관측 변경까지 섞이므로 승인 대상으로 사용하지 않는다. 현재 단계는 패키지 설계·검증 기준까지이며 적용 가능한 최종 선별 꾸러미 생성/격리 검사는 남아 있다.

전후 측정은 위 v2 12개 입력·좌표·조건·한도를 유지하고 새 배포 직전 baseline을 한 번 더 측정한다. 데이터 변화 분리를 위해 운영 내 read-only 평가 process에서 후보를 수집해 이전/새 코드 양쪽에 같은 snapshot을 전달하되 snapshot 원문은 로그/문서로 내보내지 않는다. 순서에 따른 캐시 효과를 교차하고 최소 5회씩 확보해 paired count/latency 분포를 보고한다. 12개로 서비스 전체 p95를 주장하지 않고 운영 집계 p95는 별도 표본 기간으로 측정한다.

각 후보 단계는 retrieval provenance→strict identity status→현재 Evidence/PlaceTag 분리→필수조건별 TRUE/UNKNOWN/CONFLICTED→gate→shortlist→rank→final로 계측한다. 개인정보 없는 요청 내 랜덤 키, 병합 전후 unique count, 제외 원인과 stage 시간을 별도 유지한다. 기존 alias 중복 수를 unique 장소 수로 오해하지 않도록 schema를 확정해야 한다. 확인 결과수·필수조건 위반·false identity·중복·0건·같은 후보 gate 후 생존·latency를 동일 기준으로 비교한다.

수용/복구 제안(운영 승인 전 합의 필요):

- 기본 결과의 필수조건 위반/UNKNOWN·부분 충족 오표시/false identity 1건이면 즉시 중단·복구.
- 같은 후보 입력에서 A의 gate 통과 확인 후보가 기존보다 이유 없이 소실되면 실패. 서울 근거 없는 조건은 0 유지가 정상이며 결과수 늘리기만을 성공 기준으로 삼지 않는다.
- 기존 배포 SHA/설정/정상 health/공개 검색을 적용 전 기록, 파일별 백업과 복구 SHA 재검증. identity/trace/metrics는 flag off 가능하나 A는 이전 파일/이미지 복원 후 Django health·같은12개·공개 홈/검색을 직접 재검증.
- 운영 5xx/timeout 증가 또는 paired 지연 중앙값20% 이상 증가, 운영 p95 20% 이상 증가를 중단 제안값으로 둔다. 측정 표본/기간과 합의된 기준 없이는 자동 성공 선언하지 않는다.
- AI 파일럿 후속 승인은 최대1쿼리/3후보 외에 retry 포함 HTTP 총횟수, 전역 동시성·일일 예산, 전체 deadline, exception redaction, cache scope, 중단 threshold가 필수다. 공급자키/AI플래그를 이번 작업에서 켜지 않았다. 추후 Top5 순증은 baseline과 동일 후보 identity로 중복 제거한 **새 확인 장소**만 센다.

## 5. 완료와 남은 일

완료: 파일 단위 운영/로컬 분리, local ref 전체 동일성 확인, identity 안전 수정, 102개 관련 검사, 운영 설정·hash 확인, 개인정보 없는 12개 통제 baseline, 전후 비교·복구·승인 범위 작성.

남은 일: 최신 remote의 부분 patch 중복 확인(통합 담당), A 선별 꾸러미·격리 검사 및 PostgreSQL 공간 조회 비용 검증, B funnel schema 보완과 false match 평가, C의 수집 영향/독립성 정책 합의, D 전역 비용·deadline·예외 보호와 실제 공급자 평가. 운영 배포/AI 활성화는 별도 승인 단계다.

**다음 한 가지 행동:** 운영 일치 SHA를 base로 A의 두 변경만 선별한 패키지를 만들어 격리 환경에서 12개 동일 후보 회귀와 PostgreSQL 조회 비용을 검증한다.
