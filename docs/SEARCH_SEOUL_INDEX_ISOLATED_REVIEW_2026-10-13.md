# 서울 후보 선택용 covering 인덱스 격리 검증

2026-10-13. **안정 상태에서 조건부 개선 확인, 운영 지연 해결·배포 완료는 아님.** 제품 소스·운영 DB·migration·설정은 변경하지 않았다.

## 범위와 비교 방법

- PostgreSQL 17.11 Windows 임시 전용 클러스터, loopback 주소·동적 포트·data_directory를 실제 SQL로 검증. 기존 운영 환경은 PostgreSQL 16.4였으므로 버전/OS 차이를 둔다.
- 개인정보 없는 합성 Place 250,000행·cafe 21,739행, 넓고 분산된 heap 약354MiB. 서울 선택 범위 10,869행은 앞서 운영 관측 10,752행과 가까운 규모다. 운영 원본 복사·Kakao/API 호출은 하지 않았다.
- baseline/covering 독립 schema에 같은 데이터와 기존 인덱스. covering만 `(category,lat,lng) INCLUDE(id)` 추가, 13,516,800bytes(12.89MiB). 기존 인덱스는 유지.
- **동일 v6 코드**로 부산/서울×6개 조건×5회 교차 실행. 원시 결과 파일의 v5/v6 레이블은 이번 검증에서 각각 baseline/covering 스키마를 뜻하며 코드 버전 비교가 아니다.
- 조건: 없음 / 조용함 / 콘센트있음 / 조용함+콘센트있음 / 조용함+콘센트있음+노트북작업 / 혼자이용좋음+장기체류좋음. 카페·5km·DB30·최종5. 최종 identity 순서·품질·candidate profile·필수 조건을 비교.
- 기존 12개 **검색 조건**은 유지했지만 결과 장소는 합성 fixture이며 과거 운영 12개 장소 결과를 복제한 검사가 아니다. Kakao 후보는 두 버전 모두 빈 고정 snapshot이다. 자연어 해석/외부 API/공개 HTTP 지연 검사는 아니다.
- PostGIS 확장을 설치하지 않았다. 격리 module의 supports_postgis만 true로 설정해 실제 v6의 POWER 기반 PostgreSQL 후보 선택 SQL을 실행했다. 이번 경로의 지리 함수·전체 migration 호환성은 검증 범위 밖이다.
- read-only repeatable-read 비교 중 SQL5초·lock1초 제한. fixture 구축/인덱스/ANALYZE/VACUUM/합성 갱신은 전용 클러스터에만 실행. planner 강제 선택 옵션은 쓰지 않았다.

## 결과 보존

안정 상태·최근 갱신 상태·정확한 거리 동률8행 추가 상태에서 각각60쌍/120평가, 총180쌍/360평가. **SQL 실패0, 최종 identity/순서·품질·candidate profile 불일치0, 필수조건 위반0. 모든 평가 최종5개.** 동률 probe는 이 fixture의 보존 증거이며 SQL의 동률 순서를 일반적으로 보장하는 근거는 아니다.

## 서울 반복 지연

| 상태 | 전체 처리 중앙값 기존→covering | 배치 p95 기존→covering | 최대 기존→covering |
|---|---:|---:|---:|
| VACUUM 후 안정 |147.28→107.35ms (-27.1%)|202.76→135.94ms|213.19→136.85ms|
| 카페 전체 최근 갱신 |294.71→309.07ms (+4.9%)|348.35→360.52ms|365.27→393.36ms|
| 갱신 후 동률 추가 |150.00→231.55ms|220.32→326.51ms|227.14→365.04ms|

마지막 상태는 앞선 갱신 후 cache/heap 상태를 이어받는 별도 스트레스 cohort이다. 이 숫자만으로 동률이 지연 증가의 원인이라고 단정하지 않는다. p95는 각 서울30표본 nearest-rank 배치값이며 운영 서비스 p95가 아니다.

## 개별 SQL과 실제 실행 계획

| 서울 SQL 중앙값 | 안정 기존→covering | 최근 갱신 기존→covering |
|---|---:|---:|
| 후보 선택 |26.85→3.63ms|77.83→76.365ms|
| 상세 JSON 필드 조회 |2.35→2.18ms|3.395→3.25ms|
| PlaceTag |1.60→1.36ms|1.61→1.59ms|
| 근거 품질 profile |1.63→1.545ms|1.60→1.57ms|

안정 상태 실제 EXPLAIN: 기존 Index Scan은10869행, shared hit9507/read1535,16.513ms. 새 Index Only Scan은10869행, **Heap Fetches1**, shared hit9/read135,3.173ms. Limit180·거리 정렬은 동일하며 heap 조회를 크게 줄였다.

최근 갱신 후 covering은 Index Only Scan이어도 **Heap Fetches10869**, shared read10999,77.377ms로 기존74.969ms보다 느렸다. 인덱스만 추가한다고 MVCC 가시성 확인에 필요한 heap 접근이 사라지지는 않는다. 안정 상태가 유지될 때 개선되는 후보다.

## 12개 조건별 안정 상태 중앙값

|검색|전체 기존→covering(ms)|후보 선택 기존→covering(ms)|
|---|---:|---:|
|부산-1|117.6→92.82|28.84→3.72|
|부산-2|151.18→108.02|26.86→3.37|
|부산-3|154.4→106.54|36.75→3.37|
|부산-4|157.84→114.9|21.2→3.58|
|부산-5|159.75→121.42|34.98→3.41|
|부산-6|153.52→111.25|20.4→3.69|
|서울-1|121.68→94.75|35.3→4.08|
|서울-2|138.23→96.86|21.76→3.6|
|서울-3|128.06→100.84|31.58→3.6|
|서울-4|160.27→111.05|21.23→3.57|
|서울-5|156.6→115.14|34.05→3.5|
|서울-6|157.72→108.22|20.65→3.62|

12개 모두 전체 중앙값 감소. [모든 상태별·조건별 수치](../runtime/search-index-isolated-20261013/per-case-summary.json).

## 전용 서버 재시작과 쓰기 부담

전용 PostgreSQL을 반복 중지/시작해 shared_buffers만 비운 뒤 서울 선택 SQL을3쌍 번갈아 실행했다. OS 파일 cache는 비우지 않았으므로 물리 디스크 완전 cold 검사가 아니다. 첫 EXPLAIN statement wall time 중앙값 **116.182→14.668ms**. read blocks11039→135, 선택180개 identity 순서 hash도3쌍 모두 같았다. EXPLAIN/연결 계획 비용 포함이며 전체 검색 cold 지연으로 해석하지 않는다.

1000행×5회 교차 검사·각 transaction rollback: 비 key 갱신135.147→160.590ms, 좌표 key 갱신87.647→163.646ms, 삽입88.533→140.153ms. 추가 인덱스 유지 비용이 있었다. 짧은 합성 쓰기 검사이며 운영 write TPS 예측은 아니다.

## 검증 오류와 종료 확인

초기 제한 initdb60초 timeout은 새 경로로 복구했다. 초기 fixture에서 EvidenceReview 누락으로120평가가42P01 실패했으며 유효 결과에서 제외하고 invalid-initial-all-visible.json으로 보존했다. 그 후 모든 카페에 근거를 붙인 과밀 fixture가5초 timeout을 발생시켜 자기 전용 backend만 종료하고 현실적인 근거 밀도로 줄였다. 이러한 실패를 성공 표본에 섞지 않았다. 최종3개 cohort는 모두 실패0이다.

전용 pg_ctl fast stop 성공, metadata/extra-results stopped=true, data-final/postmaster.pid 부재 확인. 공유 orchestrator SHA256은 이전과 같은0d488e9b7d998a7bc3522c3f9c69493cf7d933170a1409d354940300e7b5a669. 공유 제품 source·운영·migration·배포·commit/push 변경 없음.

[집계](../runtime/search-index-isolated-20261013/summary.json), [실행 계획·격리 주소](../runtime/search-index-isolated-20261013/metadata.json), [재시작·쓰기](../runtime/search-index-isolated-20261013/extra-results.json), [SHA manifest](../runtime/search-index-isolated-20261013/manifest.json). 최초 구축은 run.py, 보완 후 실제 유효 측정은 final.py, 추가 측정은 extra.py. reproduce-clean.py는 보완한 신규 경로 재현용 초안으로 compile만 확인했으며 추가 재실행하지 않았다.

## 판단과 다음 행동

**인덱스는 안정 데이터의 후보 선택 비용을 줄이는 조건부 후보다.** 결과 보존은 이 합성 fixture에서 확인했지만 최근 갱신/쓰기 부담 및 버전·OS·데이터 규모 차이가 있어 즉시 운영 채택하지 않는다. 과거 운영4.82초 재현/해결을 이번 로컬 결과로 선언하지 않는다. 기존 v6 패키지를 유지한다.

**다음 한 가지 행동:** 운영과 같은 PostgreSQL16.4의 격리 환경에서 실제 규모·근거 분포를 반영하고 갱신 후 가시성 회복 구간을 포함해 인덱스 후보를 재검증한다.

후속: [PG16.4 실제 규모·근거 분포·가시성 회복 재검증](SEARCH_SEOUL_PG164_VISIBILITY_REVIEW_2026-10-13.md)에서5상태300쌍/600평가결과보존을확인했다. 자동회복뒤후보SQL은개선되지만서울전체지연의일관된개선은미입증이다. 운영변경없음.
