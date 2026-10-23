# PostgreSQL16.4 실제 규모·근거 분포와 가시성 회복 검증

**조건부 후보 유지. PostgreSQL16.4에서 결과 보존과 가시성 회복에 따른 선택 비용 감소를 확인했다. 운영4.82초 해결·배포 완료는 아니다.**

## 격리와 실제 규모

- 2026-10-13 운영 SSM 읽기 전용 집계 성공. repeatable-read/read-only·SQL5초/lock1초 제한, 장소 이름·좌표·원문·사용자 정보를 반출하지 않고 집계만 보존했다. 버전16.4(Debian), shared_buffers128MB, 자동 정리 threshold50/scale0.2/naptime1min/cost_delay2ms를 확인했다.
- 같은 server_version_num160004의 PostgreSQL16.4 Windows 포터블 임시 클러스터를 사용했다. loopback·동적포트·workspace data_directory를 실제 SQL로 검증하고 dotenv를 차단했다. 격리 구축용 max_wal_size는4GB이며운영값과동일하다고검증하지않았다. 운영과 버전/버퍼/자동 정리 기본값을 맞췄지만 OS·저장장치·동시 부하는 다르다.
- 전국 규모는 운영 pg_class reltuples 추정값을 사용해 Place1,257,991·PlaceTag863,623·Evidence291,067행을 합성했다. 격리에서 실제 count를 직접 검증했다. 운영 전국 exact count로 오해하지 않는다.
- 서울/부산 카페 bounds count는 운영 직접 exact count10752/5553을 반영했다. 전국 카테고리 분포와 실제 좌표/공간 상관관계는 복제하지 않았다. 합성 도시 좌표·배경 카테고리·물리적 행 배치는 재현용 분포다.
- 운영 각 도시 nearest180의 다섯 필수 조건 태그/근거에 대해 source·상태·verified·confidence10단위·극성·만료와 verified 조합 분포를 집계해 반영했다. 다른 태그는 기타 그룹으로 합쳐 합성 카페 기본 사실로 대체했다. 서로 다른 태그/근거의 실제 장소별 연결·원문·독립 출처는 복제하지 않았다. 따라서 운영 전체 근거 상관관계와 동일한 fixture라고 선언하지 않는다.
- 서울180개 모두 다섯 조건의 verified 조합이0. 부산176개0,1개콘센트+노트북,1개노트북,2개콘센트. 만료/미확인/부정 근거를 유지했고 임의로 긍정 근거로 승격하지 않았다. 전국 배경 태그/근거는 읽기/인덱스 규모를 맞추는 합성 기본 사실이다.
- 초기 Place heap874807296bytes vs 운영900464640bytes(-2.85%). 추가 인덱스62570496bytes(59.67MiB, 추가 공간). 아래 auto 결과에는 갱신 후 실제 heap/index 크기도 별도 있다.

## 동일12개 비교

동일 v6 orchestrator, 부산/서울×6조건×5회 교차 비교. 원시 v5/v6는 코드 버전이 아니라 기존/covering schema 레이블이다. 두 schema의 코드/데이터는 같고 covering만 `(category,lat,lng) INCLUDE(id)` 추가했다. 기존 인덱스 유지·planner 강제 옵션 없음. PostGIS bool만 true로 하여 실제 PostgreSQL POWER 선택 SQL을 실행했고 지리 확장/전체 migration 호환성 검사는 하지 않았다.

검색 조건은 없음/조용함/콘센트있음/조용함+콘센트있음/조용함+콘센트있음+노트북작업/혼자이용좋음+장기체류좋음. 카페5km·DB30·최종최대5. Kakao는 고정 빈 snapshot, AI/웹/쿼리수정 호출을 끈 통제 검색이며 실제 운영 장소 결과·외부/API/자연어/HTTP 지연의 복제는 아니다.

상태5개×60쌍 = 300쌍/600평가. 실패0·identity순서/품질/profile 불일치0·필수조건 위반0.

서울 기본 검색5개/나머지0개, 부산 기본5개·조용함1개·콘센트2개·복합0개로 모든 회차/상태에서 동일하다. 근거가 없으면0개를 유지하며5개를 채우지 않았다. 빈 결과 비교의 한계가 있지만 기본/부산 단일 조건은 non-empty 결과 identity·품질을 비교했고 모든 검색에서 DB후보 profile도 비교했다.

## 서울 전체·선택 지연

| 상태 | 전체 중앙값 기존→covering(ms) | 배치 p95 기존→covering(ms) | 선택SQL 중앙값 기존→covering(ms) |
|---|---:|---:|---:|
|초기 안정|159.625→140.97|223.83→205.79|44.015→3.445|
|16305행 갱신 직후|92.595→92.63|278.29→262.68|4.38→4.63|
|갱신 후65초 대기|87.415→89.725|123.68→122.84|4.145→4.415|
|명시적 VACUUM 회복|91.0→86.51|139.79→129.83|4.125→3.16|
|300000행 갱신 후 자동 회복|100.705→104.38|145.09→183.76|5.035→3.31|

각 값은 동일 상태 내의 교차 비교이며 상태 사이 차이를 인덱스 효과로 계산하지 않는다. 초기 안정 대비 이후 기존 인덱스도 빨라졌다. 실제 EXPLAIN에서 기존 heap logical buffer10824→1060이 관측돼 갱신 후 물리적 배치/캐시 효과도 개입한다. 한 요인인 가시성만으로 전체 차이를 설명하지 않는다. p95는 서울30표본의 nearest-rank 배치값이다.

초기 안정 서울 전체11.69% 감소, 선택44.015→3.445ms. 갱신 직후 전체92.595→92.630ms로 사실상동일, 대기후87.415→89.725ms로소폭회귀. 명시적 회복후91.000→86.510ms로4.93%개선. 초기 표본의 큰 이득이 매상태 유지되지는 않는다. 자동 회복 후에도 전체 중앙값100.705→104.380ms(+3.65%),배치p95145.09→183.76ms로관측상회귀했다. 후보SQL이빨라져도전체검색이일관되게빨라지는효과는입증하지못했으므로운영채택을권고하지않고조건부연구후보로남긴다. 상세 조회 중앙값1.7~3.7ms 수준은 선택 인덱스의 직접 개선 대상이 아니다.

## 가시성 회복의 직접 증거

- 초기 cover Index Only Scan Heap Fetches0,10752행. 갱신 직후10752,65초뒤10752,명시적VACUUM뒤0. 명시적회복 계획 shared hit198·read0·execution2.774ms. warm EXPLAIN은 반복검색 전체latency와다른표본이다. 합성좌표/카테고리상관관계로planner Rows1 vs Actual10752의심한추정오차도있어운영planner분포와동일시하지않는다.
- 검색 카페16305행만갱신한경우 n_dead_tup16305와autovacuum_count가65초뒤에도동일했다. 약125.8만행의기본dead threshold는약25.2만행이므로기준미달이다. 한분대기만으로자동회복하지않는것을이격리표본에서직접확인했다. 명시적VACUUM뒤dead0및HeapFetches0을확인했다.
- 별도positive control에서각schema300000행갱신으로기본기준을넘겼다. 첫180초에는가시성map의부분회복만관측했고완전회복을확정하지않았다. 서버종료후재시작하여추가갱신없이최대180초이어관찰했다. 기존쪽완료/covering쪽인덱스정리단계를확인한후최대300초의최종종료관측을했다. 아래count/dead/VM과worker phase로완전회복여부를판단하며불완전하면불완전으로기록한다. 여러관측구간은서버중지/재시작을사이에둔비연속관측이고재시작이worker주기를바꾸므로운영회복시간으로해석하지않는다.

이어관측에서 완전 완전 자동 회복 관측: **True**. 마지막 관측 elapsed=130.06초.

첫관측170초: baseline/covering all-visible 105835/85162, 초기69772/69772에서부분회복. 다음180초관측에서baseline dead0·auto count2로완료,covering은vacuuming indexes단계·dead300000/HeapFetches4150으로미완료였다.

|자동관측 경과(초)|baseline dead / auto count|covering dead / auto count|baseline/covering all-visible page|
|---:|---:|---:|---:|
|0|0/2|300000/0|131790/105835|
|0.0|0/2|300000/0|131790/105835|
|0.0|0/2|300000/0|131790/105835|
|10.01|0/2|300000/0|131790/105835|
|20.01|0/2|300000/0|131790/105835|
|30.01|0/2|300000/0|131790/105835|
|40.03|0/2|300000/0|131790/105835|
|50.03|0/2|300000/0|131790/105835|
|60.03|0/2|300000/0|131790/105835|
|70.03|0/2|300000/0|131790/105835|
|80.05|0/2|300000/0|131790/105835|
|90.05|0/2|300000/0|131790/109726|
|100.05|0/2|300000/0|131790/115558|
|110.05|0/2|300000/0|131790/121397|
|120.06|0/2|300000/0|131790/127217|
|130.06|0/2|0/1|131790/131790|

실제worker progress 40.03초: [['covering', 'scanning heap', 131790, 4283, 0]]

실제worker progress 50.03초: [['covering', 'vacuuming indexes', 131790, 131790, 0]]

실제worker progress 60.03초: [['covering', 'vacuuming indexes', 131790, 131790, 0]]

실제worker progress 70.03초: [['covering', 'vacuuming indexes', 131790, 131790, 0]]

실제worker progress 80.05초: [['covering', 'vacuuming indexes', 131790, 131790, 0]]

실제worker progress 90.05초: [['covering', 'vacuuming heap', 131790, 131790, 3890]]

실제worker progress 100.05초: [['covering', 'vacuuming heap', 131790, 131790, 9722]]

실제worker progress 110.05초: [['covering', 'vacuuming heap', 131790, 131790, 15561]]

실제worker progress 120.06초: [['covering', 'vacuuming heap', 131790, 131790, 21381]]

이어관측종료후baseline 선택warm EXPLAIN 29.769ms,HeapFetches=None.

이어관측종료후covering 선택warm EXPLAIN 6.144ms,HeapFetches=0.

## 보존·한계·판단

대용량 합성 생성 초기 int overflow 실행은 중단/전용서버종료 후새경로에서bigint로보완했고유효비교에서제외했다. 운영집계SSM Success와필수SQL성공을확인했다. 운영DDL/DML/VACUUM/설정/서비스/배포·migration·제품소스·commit/push변경없다. 전용클러스터main/auto 종료확인(stopped true,postmaster.pid부재).

추가 인덱스는 가시성 회복 후 heap 접근을 없애는 **조건부 후보**다. 16.4·전국테이블규모·희소근거를반영해도소규모갱신뒤자동회복은기본설정에서관측되지않았다. 회복뒤이득도물리배치/캐시에따라다르며, 운영4.82초저장장치/동시부하지연해결을확정하지않는다. 기존v6를유지한다. 앞선PG17의쓰기비용증가는이번버전에서재측정하지않았으므로새수치로인용하지않는다.

[운영 집계](../runtime/search-index-pg164-20261013/production-aggregates.json), [12개·반복 집계](../runtime/search-index-pg164-20261013/summary.json), [가시성·실행 계획](../runtime/search-index-pg164-20261013/metadata.json), [첫 부분회복 관측](../runtime/search-index-pg164-20261013/auto-results.json), [첫 이어관측·worker phase](../runtime/search-index-pg164-20261013/auto-continuation-results.json), [최종 종료관측·실제 count·heap](../runtime/search-index-pg164-20261013/auto-final-results.json), [hash manifest](../runtime/search-index-pg164-20261013/manifest.json).

**다음 한 가지 행동:** 인덱스 생성·복구·부하 제한과가시성관측을포함한운영적용후보계획을준비한다. 운영실행은별도승인범위다.
