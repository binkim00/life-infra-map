> 후속: [covering 인덱스 격리 검증](SEARCH_SEOUL_INDEX_ISOLATED_REVIEW_2026-10-13.md) 완료. 안정 상태 개선·최근 갱신 회귀로 조건부 후보이며 운영 변경 없음.

# 서울 선택·상세 SQL 지연 진단과 수정 검토 — 2026-10-13

## 결론과 현재 후보

**지연이 후보 선택의 heap I/O 경로에서 발생하는 증거를 확보했다. 코드 수정 두 안은 채택하지 않았다.** v7은 동률 결과를 바꿨고 v8은 결과를 보존했지만 더 느려졌다. 유지할 검색 후보는 이전 v6이다. 4.82초 원표본에는 개별 SQL 기록이 없어 당시 한 SQL/대기 원인을 소급 확정할 수 없으며, 이번 관측과 구분한다.

운영 서비스/설정/인덱스/데이터/마이그레이션을 변경하지 않았다. 공유 orchestrator SHA `0d488e9b7d998a7bc3522c3f9c69493cf7d933170a1409d354940300e7b5a669` 보존, checkout/index/commit/push 변경 없음. 현재 작업은 읽기 전용 진단·로컬 코드 실험까지이며 **실제 성능 문제의 해결은 미완료**다.

## 개별 계측

서울 중심(37.5665,126.9780), 카페, 필수조건 없음, 5km, DB기본30 조건에서 collect5회를 실행했다. SQL 원문/params/장소명/주소/인용문/사용자 정보는 저장하지 않았다. QUERY별 ordinal·분류·시간과 허용한 plan 필드/숫자만 저장했다.

기존 '선택·상세3개 SQL'은 실제로 **후보 선택, 상세 JSON annotation, 작은 Tag metadata 조회**였다. PlaceTag와 Evidence profile은 별도 query다. 초기 generic label other였던 ordinal1은 plan으로 bounded_selection임을 확인해 [보정 집계](../runtime/seoul-sql-diagnosis-labeled-20261013.json)에 명시했다. [원 집계](../runtime/seoul-sql-diagnosis-20261013.json)도 보존했다.

| SQL 역할 | 5회 실행시간 범위 | warm EXPLAIN 실행 | 주요 plan |
| --- | ---: | ---: | --- |
| bounded candidate selection | 15.635~489.670ms | 15.876ms | Bitmap Heap Scan→top-N sort→limit180 |
| 상세 JSON annotation | 2.795~10.725ms | 0.717ms | Place PK index scan180행 |
| PlaceTag 조회 | 2.084~20.992ms | 0.393ms | place FK index124행 |
| Tag metadata | 0.500~4.625ms | 0.041ms | 작은 tag table9행 |
| Evidence profile | 2.346~7.867ms | 0.663ms | place FK index→Tag join |

선택 query는 planner estimate2,834 대비 actual10,752행을 읽고180개를 반환했다. category/lat/lng 인덱스를 사용했지만 Bitmap Heap Scan이 필요했으며 warm plan shared hit6,623 blocks, temp written0, top-N sort33KB였다. 디스크 sort spill이 아니라 테이블 페이지 접근이 큰 경로다.

별도 **읽기 전용 observer connection**이 같은 진단 backend의 wait_event만25ms 간격으로 관찰했다. 후보 선택에서 DataFileRead17표본·DataFilePrefetch1표본, 상세/PlaceTag에서 DataFileRead 각1표본을 확인했다. 표본 수는 정확한 I/O 밀리초나 대기 비율이 아니다. Python 중 ClientRead는 application이 DB를 기다리는 CPU 증거가 아니므로 CPU 병목으로 분류하지 않았다.

track_io_timing은 off였다. 켜거나 운영 설정을 바꾸지 않았으므로 정확한 read 시간은 미계측이다. warm EXPLAIN은 read blocks0이지만 실제 timed query에서 I/O wait가 관측됐다는 것을 같이 기록한다. EXPLAIN 직전 cache가 이미 따뜻해졌으므로 warm plan의15.876ms로489ms/4.82초가 해결됐다고 주장하지 않는다.

## 확인한 스키마와 인덱스 제약

모델과 migration 이력(초기 category/lat/lng 인덱스,0003 rename,0008 lat/lng,0029 검색 인덱스) 및 현재 운영 pg_indexes를 읽었다. [메타데이터 집계](../runtime/seoul-index-metadata-20261013.json)에서 기존 범위 인덱스는 `(category, lat, lng)`이고 `id` INCLUDE가 없다. name/address trgm, PK, unique source/external_id, geo index도 존재하므로 '인덱스가 전혀 없다'는 진단은 아니다.

선택 query는 범위 필터와 정렬용 lat/lng 외에 반환할 id가 필요하다. 이 모든 열이 인덱스에 있어야 index-only scan이 가능하고, MVCC visibility map도 만족해야 실제 heap 접근을 피할 수 있다. [PostgreSQL 공식 설명](https://www.postgresql.org/docs/current/indexes-index-only-scans.html).

현재 catalog 추정은 relpages109,920 / relallvisible109,898 / reltuples1,257,991이다. 테이블 전체 all-visible 비율은 약99.98%로 covering index 검토 근거가 되지만, 서울 선택 범위의 실제 Heap Fetches 감소나 성능 수치를 증명하지는 않는다. 이 숫자는 catalog 추정이며 별도 COUNT/DB 변경을 하지 않았다.

## 코드 실험과 제외 사유

가까운 bbox에서 먼저 nearest180을 읽고, kth 거리값이 모든 바깥 후보의 최소 가능 거리보다 엄격히 작은 경우만 종료하는 일반적인 progressive selection을 구현했다. 특정 서울/장소를 hardcode하지 않고 요청 bounds 안에서만 실행한다. 증명 실패/희소한 경우 전체 원래 bounds로 복귀한다. 단위 검사에 조기 종료, 사각형 corner 밖의 더 가까운 장소, 희소 fallback, 동률 원래 조회 복귀를 넣었다.

고유 **97개 회귀 통과**, compile/AST/patch/hash 검증. SQLite 회귀가 운영 결과 보존을 대신하지 않는다는 점은 아래 실제 비교에서 확인됐다.

### v7 — 결과 회귀로 제외

v6/v7 동일12개×5회,60쌍 비교의 오류/필수조건 위반은0이었다. 그러나 candidate profile membership 불일치50쌍, 최종 identity/quality 불일치5쌍(서울 조건 없는 검색5회)이 있었다. 새 id tie breaker와 범위 sort가 기존 동률 순서를 바꿀 수 있어 결과 보존 기준을 만족하지 못했다. 속도가 개선된 숫자가 있어도 채택하지 않았다.

[실험 결과](../runtime/search-package-a-v7-20261013/repeat-summary.json), [제외 표시](../runtime/search-package-a-v7-20261013/DECISION.md). 이 패키지는 통합/배포 대상이 아니다.

### v8 — 결과 보존, 성능 회귀로 제외

선택 창의 거리값에 동률이 있으면 원래 전체 query/ordering으로 즉시 복귀하도록 보완했다. v6/v8 동일12개×5회,60쌍/120평가에서 실패0·candidate profile/결과 quality/identity 순서 불일치0·조건 위반0을 확인했다.

하지만 전체 median289.65→356.61ms(+23.1%), 배치 p951,188.44→2,395.04ms, 최대2,535.69→4,876.86ms였다. Seoul1 median399.99→593.32ms로 증가했다. 동률 fallback 때문에 추가 probe 비용을 지불하고 큰 전체 scan도 다시 수행했다. 결과를 보존하기 위해 필요한 보수성이 성능 목표를 충족시키지 못했다.

v8 최대는 서울1 첫 반복4,876.86ms, bounded selection SQL2회 합계4,429.23ms였다. 상세/Tag metadata 합계87.99ms, PlaceTag96.63ms, profile42.84ms였다. 따라서 이번4.8초 재발은 적어도 **bounded selection query 집합**에 위치한다. 그 두 query 각각의 원인/시간은 반복 비교 aggregate만으로 확정하지 않지만, 앞선 개별 query/observer 관측은 전체 scan의 heap I/O 병목을 지지한다.

[실험 결과](../runtime/search-package-a-v8-20261013/repeat-summary.json), [제외 표시](../runtime/search-package-a-v8-20261013/DECISION.md). v8도 통합/배포하지 않는다. 배치 p95는 운영 서비스 p95가 아니며 회차별 baseline을 섞지 않았다.

## 다음 개선안의 구체적 범위

[covering index 격리 검증 SQL 초안](../runtime/seoul-covering-index-isolated-plan-20261013.sql)을 작성했다. 후보는 기존 검색 key `(category,lat,lng)`에 payload `id`를 포함하는 인덱스다. 기존 인덱스/적용 migration은 삭제·재작성하지 않는다.

격리 PostgreSQL의 개인정보 없는 fixture로 기존/covering plan의 Index Only Scan·Heap Fetches·buffer·정렬/동률 identity·지연·index 크기·삽입/갱신 부담을 비교해야 한다. all-visible과 최근 갱신 상태를 둘 다 평가하고, planner가 새 index를 선택하지 않는 경우도 결과로 남긴다. 기존 동률 의미/identity가 바뀌면 임의로 승인하지 않는다.

SQL은 **검토 초안이며 실행하지 않았다**. 운영 생성/ANALYZE/VACUUM/설정/마이그레이션 변경은 사용자 원래 지시의 승인 범위를 벗어나므로 실행하지 않았다. 운영 적용은 격리 검증과 실제 변경 계획·복구·영향 범위가 준비된 후 별도 승인 단계다. 현재 개발 환경에서 Docker CLI는 발견됐으나 격리 PostgreSQL 실행/인덱스 검증은 이번 응답에서 완료하지 않았다.

## 완료·남은 일·다음 행동

완료: 개별 SQL5회·EXPLAIN/버퍼·wait event 관측, 스키마/index/catalog 읽기 전용 대조, 병목 범위 축소, progressive selection2종 구현·97개 회귀·각60쌍 운영 메모리 비교, 결과/성능 회귀 확인 후 두 안 제외, covering index 격리 검증 초안 작성. 공유 source는 보존하고 v6를 유지했다.

남은 일: 실제 covering index의 격리 성능·동률·갱신 비용 검증. 4.82초 과거 표본의 정확한 개별 wait 원인은 기록 부족으로 확정 불가하며, I/O의 저장장치/동시 부하 기여는 미분리다. 코드 기반 성능 개선을 완료했다고 선언하지 않는다.

**다음 한 가지 행동:** 별도 격리 PostgreSQL fixture에서 covering index의 plan·Heap Fetches·동률 identity·지연·갱신 부담을 검증한다.
