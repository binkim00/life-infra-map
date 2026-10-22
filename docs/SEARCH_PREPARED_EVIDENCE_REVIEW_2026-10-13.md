# 검색 근거 반복 계산·서울 지연 개선 — v6 검증 (2026-10-13)

> 최신 후속: [서울 개별 SQL·I/O 진단](SEARCH_SEOUL_SQL_TAIL_REVIEW_2026-10-13.md). 첫 선택 query의10,752행 Bitmap Heap Scan과 DataFileRead 대기를 확인했다. v7은 결과 identity 회귀, v8은 성능 회귀로 제외했으며 v6 유지. covering index 격리 검증 초안을 작성했지만 실제 index/마이그레이션/운영 변경은 하지 않았고 tail 해결은 미완료다.

## 결과

**반복 근거 계산의 비용을 줄였고 12개 검색 모두 중앙 시간이 개선됐다.** v5/v6의 같은12개×5회 교차 비교(60쌍/120평가)에서 전체 서버 평가 중앙값508.39→244.30ms(-51.9%), retrieval423.89→167.57ms(-60.5%), 장소별 근거 판정 합산 wall274.61→19.70ms(-92.8%)를 관측했다.

실패0, 후보별 근거 프로필·최종 품질·identity 순서 불일치0, 필수조건 위반0이다. 서울6개 median도 모두44.8~61.0% 줄었다. 단, v6의 서울 조건 없는 카페 검색에서4,816.21ms 단발 지연이 있었다. 중앙값 개선과 서울 최대 지연 해소를 구분한다. 실제 운영 배포/서비스 지연 승인 완료는 아니다.

## 최종 수정과 패키지

[검토용 v6 패키지](../runtime/search-package-a-v6-20261013/search-package-a.tar.gz), [manifest](../runtime/search-package-a-v6-20261013/manifest.json), [diff](../runtime/search-package-a-v6-20261013/change.patch), [후보 source](../runtime/search-package-a-v6-20261013/candidate/backend/recommendations/services/ai_search_orchestrator.py).

- 후보 SHA `7fca56232ddfb021b92bc6ec88e31771b7caf04f6d0fadc5bd6df79a07279510`
- archive SHA `9904ed0a4ae2388337b344a094cf59ef2ee125afdf72db8518455e34879fe7f9`
- base/rollback SHA `cc265e7968bfc8e1d2bfb689acd1ed257fc2c9095335ca8eaf005d0e1ad1972d`
- 비교 v5 SHA `a53b6dbc42c49c3d65d0e165fbbe9d365999de28c92a5271664dd87b9cbc185e`

`_db_evidence`는 장소마다 같은 frame의 검색 용어, 원시 대상/업종 용어, category code 조합을 다시 계산했다. `_prepare_db_evidence`로 이를 **collect 요청 한 번에 한 번** 계산하고 키워드 인자 `prepared`로 장소별 평가에 전달한다. 장소 facts·태그·policy text·장소별 충족 판정은 계속 장소마다 계산한다. 요청 간/global cache나 프론트엔드 상태는 만들지 않았다. frame/context를 바꾸거나 SourceFact와 inferred tag를 합치지 않는다. 다른 직접 호출/semantic collector는 기본 `prepared=None` 경로로 새 문맥을 계산하므로 의미를 유지한다.

`_verified_required_place_ids`는 희소한 확인 태그 후보를 찾는 과정에서 공간 KNN 정렬을 사용했다. 이를 기존 category/bounds/태그 허용 정책의 SQL로 좌표만 읽고 정확한 haversine 거리·ID로 정렬하는 방식으로 바꿨다. 원시 Evidence 추가 조회와 gate는 유지하며 대략적인 거리로 조건을 통과시키지 않는다. 확인 태그가 하나라도 매칭된 후보를 발견하는 기존 정책과 최종 필수조건 전체 gate도 유지한다.

이 조회는 SQL limit 이전에 bounds 안의 확인 후보 좌표를 읽는다. 넓은 반경/확인 태그가 많은 상황은 읽는 좌표와 Python 정렬량이 늘 수 있어 고정5km 표본의 개선을 모든 지역/반경으로 일반화하지 않는다. index/schema/DB statistics/운영 설정/서비스는 변경하지 않았다.

패키지는 같은 orchestrator1파일이며 운영 base 대비 변경 함수7개다(이전 두 검색 기능·상세 통합 포함). 새 서비스 모듈·기능 플래그·AI 공급자/키·UI·수집 worker/planner·마이그레이션은 제외했다. 공유 source SHA는 `0d488e9b7d998a7bc3522c3f9c69493cf7d933170a1409d354940300e7b5a669`로 보존했다. commit/push/checkout/index 변경 및 운영 파일 적용은 없다.

## 회귀와 운영 읽기 전용 검증

최종 관련90개 검사와 신규3개 검사를 합쳐 **고유93개 통과**, system check0 issues. 새 검사:

- 준비된 문맥과 기존 fresh 계산의 판정 tuple 일치, 반복 호출에서 문맥/frame 불변, 여러 업종·제외/흡연 조건과 요청 간 격리.
- 여러 장소를 평가해도 collect에서 prepare1회.
- 확인 후보가 가까운 순으로 반환되고 PostGIS 분기에서도 KNN을 호출하지 않음.

각 검사와 준비 문맥은 [신규 회귀 파일](../runtime/search-package-a-v6-20261013/isolated/backend/recommendations/test_prepared_v6.py)에 있다. compile/AST 함수 범위/제외 기능/patch apply/manifest hash 검증 통과. 전체 backend suite나 운영 이미지 전체 검사는 아니며, 로컬 SQLite 회귀와 PostgreSQL 실데이터 평가를 구분한다.

서버에서는 확인된 base hash의 파일을 읽어 candidate를 메모리에 생성했다. REPEATABLE READ READ ONLY snapshot, statement timeout5초/lock timeout1초, 실패 savepoint/최종 rollback을 사용했다. 도시당 Kakao snapshot을 공유하고 같은 입력·frame·반경·한도로5회씩 교차 순서를 적용했다. AI reranker·AI Web Search 비활성 상태를 확인했고 바꾸지 않았다. 원문 SQL/params/장소명/주소/인용문/식별자는 저장하지 않았다.

## 반복 측정

입력은 query/primary query=카페, cafe, 부산(35.1796,129.0756)/서울(37.5665,126.9780), 반경5km, DB기본30/Kakao45/Top5, 이전6조건을 유지했다. 자연어 planner/query repair를 통제상 우회·생략했다. 시간은 공통 Kakao 최초 네트워크·HTTP·intent를 제외한 서버 retrieval→최종 평가다.

[120회 결과](../runtime/search-package-a-v6-20261013/repeat-results.json), [요약](../runtime/search-package-a-v6-20261013/repeat-summary.json), [압축 출력 실행 코드](../runtime/search-package-a-v6-20261013/repeat-compressed.py). 이전 회차의 baseline을 재사용하지 않고 이번 회차 v5/v6끼리만 비교했다.

| 시나리오 | v5 중앙ms | v6 중앙ms | 변화 | 양쪽 최종 결과수 |
| --- | ---: | ---: | ---: | ---: |
| 부산-1 | 524.95 | 247.33 | -52.9% | 5 |
| 부산-2 | 632.79 | 264.52 | -58.2% | 5 |
| 부산-3 | 523.82 | 286.47 | -45.3% | 5 |
| 부산-4 | 522.05 | 261.18 | -50% | 5 |
| 부산-5 | 553.14 | 259.82 | -53% | 5 |
| 부산-6 | 373.10 | 174.61 | -53.2% | 3 |
| 서울-1 | 481.67 | 265.88 | -44.8% | 5 |
| 서울-2 | 484.26 | 241.27 | -50.2% | 5 |
| 서울-3 | 470.23 | 192.40 | -59.1% | 5 |
| 서울-4 | 437.20 | 216.03 | -50.6% | 1 |
| 서울-5 | 509.22 | 218.16 | -57.2% | 1 |
| 서울-6 | 486.79 | 189.99 | -61% | 0 |

SQL수 중앙값은 양쪽10회로 같으며 SQL 외 장소별 공통 frame 계산을 줄인 것이 주된 관측 변화다. 확인 후보 조회 wall median은7.02→6.22ms로 작은 차이였고, 이를 전체51.9% 개선의 주원인이라고 주장하지 않는다. 근거 프로필13.24가 아닌 **이번 회차** v5 14.19→v6 13.89ms로 거의 동일하다.

장소별 근거 판정 wall은 호출별 누적 시간이며 순수 CPU time은 아니다. prepare 자체는 collect에 별도로 한 번 수행되고 이 합산 밖에 있으므로 최종 효과는 전체/검색별 wall로도 확인했다. 단계별 SQL wrapper 시간에는 모든 fetch/model 생성/Python 처리가 포함되지 않는다.

배치60표본 nearest-rank p95는930.57→568.66ms(-38.9%)지만 운영 서비스 p95가 아니다. 시나리오당5회 표본의 tail은 충분히 안정적이지 않으며 캐시/IO/동시 작업은 인위적으로 통제하지 않았다. 모든 median이 개선되어 이전 '20% 이상 느려진 case' 조건은 이번 표본에서 재발하지 않았다. 이를 바로 운영 성능 승인으로 확대하지 않는다.

## 서울 지연 변동과 한계

v6 최대 지연은 **서울1, 첫 반복4,816.21ms**였다. retrieval4,602.37ms 중 장소 선택/상세 SQL3회 합계4,375.25ms였다. 이 frame은 필수조건이 없어 확인 태그 발견0.01ms/원시 근거 발견0ms였고, 장소별 근거 판정24.30ms였다. 따라서 이 outlier를 반복 근거 계산이나 새 확인 태그 정렬 탓으로 분류하면 안 된다.

장소 선택/상세 범주의3개 SQL 중 어느 하나가 지연했는지는 이번 집계로 분리하지 못했다. 페이지 읽기·동시 부하·planner 변동은 가능 원인이지만 실측 인과 원인으로 확정하지 않는다. 해당 조건 없는 검색의 공통 선택/hydration 경로는 v5/v6에서 유지했고 운영 서비스를 restart/캐시 flush/DB 변경해 가리지는 않았다.

v5 최대1,636.88ms보다 v6 최대가 커졌으므로 '서울 tail 해소' 또는 '최악 지연 개선'을 주장하지 않는다. 중앙값과 배치 p95 개선은 확인했으나 단발 최대 지연은 남았다. 과거 HTTP200/30건 또는 새 결과35건을 이 latency 증거에 섞지 않는다. 두 버전의 조건 검색35건은 검색별 합계이고 AI/고유 장소 수가 아니다.

## 완료·남은 일·다음 행동

완료: 요청 내 공통 근거 계산 재사용, 확인 태그 KNN 제거·정확 거리 보존, 관련93개 회귀, 같은12개×5회 전후 검증, 실패/불일치/위반0, 모든 scenario median 및 배치 p95 개선 관측, 검토 패키지/rollback/manifest/diff 작성. 운영 적용은 하지 않았다.

남은 일은 서울 조건 없는 검색의 단발 최대지연을 개별 SQL 단위로 나누고 IO/plan 증거를 확보하는 것이다. 운영 이미지 확인·배포 승인은 별도 단계로 남긴다.

**다음 한 가지 행동:** 서울 조건 없는 카페 검색의 선택·상세3개 SQL을 원문 없이 개별 계측하고 plan/buffer/IO를 읽기 전용으로 대조해 단발 지연 원인을 확인한다.
