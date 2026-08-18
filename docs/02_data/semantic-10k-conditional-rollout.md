# Conditional Semantic 10K 결과와 운영 전환 Runbook

기준일은 2026-08-18이다. 기존 Structured Intent 기반 `semantic_required`
구현은 변경하지 않았으며, 운영 PostgreSQL에는 pgvector extension이나 vector
migration을 적용하지 않았다. 운영 기본값은 Retrieval OFF, Candidate Injection
OFF, Semantic weight 0.10이다.

## 10K 층화 표본

표본은 random sampling이 아니라 Region, Category, Feature cluster를 순환하는
결정적 층화 방식으로 선택했다. current active positive Evidence가 있고 negative
Evidence가 없는 Canonical Feature만 사용했다.

- Region: 서울 1,846, 부산 1,791, 인천 1,835, 대구 1,762, 대전 1,103,
  광주 700, 울산 963.
- Category: cafe 442, restaurant 3, city_park 500, library 842, parking
  1,496, shelter 3,001, toilet 3,682, tourism 34.
- Feature cluster: work 63, solo/social 298, outdoor 584, facility 4,528,
  other 4,527.
- 부족 cell: restaurant 3, tourism 34, work 63. 공급 부족을 가짜 데이터로
  보충하지 않았다.
- 같은 범위의 eligible Place는 19,257개이며 표본은 51.93%다.

## FeatureDocument와 embedding

문서는 Place name, Category, Region, active positive Canonical Feature만 포함한다.
AI 설명과 추천 이유는 포함하지 않는다.

- FeatureDocument: new 2,870, updated 0, unchanged 7,130, skipped 0.
- Embedding 대상 10,000, 기존 재사용 1,013, 신규 8,987, 실패 0.
- Provider/model: OpenAI `text-embedding-3-small`, 512 dimensions, contextual.
- API batches 90, input tokens 302,763.
- 비용 USD 0.00605526. 공식 가격 USD 0.02 / 1M input tokens 기준이다.
- embedding 107,598.95ms, 운영 JSON DB 저장 24,600.75ms.
- 즉시 재실행: unchanged 10,000, API calls 0, tokens 0, cost 0.
- source hash가 달라질 때만 다시 호출되는 경로를 회귀 테스트로 검증했다.

가격 기준: https://developers.openai.com/api/docs/models/text-embedding-3-small

## 별도 pgvector staging

`docker-compose.pgvector-staging.yml`은 PostgreSQL 16 + PostGIS 3.4 + pgvector
0.8.6을 사용한다. 운영 compose, 운영 volume, 운영 network를 연결하지 않는다.
호스트 포트는 55433이며 별도 named volume/network를 사용한다.

- rows 10,000, duplicate document/place ID 0.
- metadata/vector dimension error 0, source hash mismatch 0.
- 동일 내용으로 인한 source hash 중복 group 142개는 row 중복이 아니다.
- import 2,800.84ms, HNSW build 4,395.45ms, ANALYZE 31.01ms.
- HNSW index 26MB, table+indexes 55MB.
- Top-K host SQL latency: K5 62.62ms, K10 60.45ms, K20 59.83ms,
  K50 60.77ms.
- 기본 planner는 10K에서 sequential scan을 선택해 Top-20 32.486ms였다.
- HNSW 강제 plan은 `semantic_pilot_embedding_hnsw`를 사용해 0.452ms였다.

staging table은 feature document ID, place ID, vector, provider, model,
dimensions, strategy, source hash, embedded timestamp를 분리 저장한다. 운영
`PlaceFeatureEmbedding` migration은 만들거나 적용하지 않았다.

## OFF vs Conditional ON 50 Query

실제 실행은 OFF, weight 0.10 cache miss, weight 0.10 cache hit만 비교했다.
0.15와 0.20은 재실행하지 않았다.

- semantic_required 27, skipped 23. skipped embedding API calls 0.
- 결과 변경 10, no-result OFF/ON 모두 22.
- Hard/Category/Region violation 0/0/0.
- duplicate 0, unsupported reason 0.
- 기존 변경 14 Query 중 9개가 변경되고 5개가 동일했다.
- 잘못 활성화된 단순 Region+Category Query는 발견되지 않았다.
- 명확한 의미 Query 누락은 16개다. 혼밥, 데이트, 대화, 장기체류/작업,
  혼자 이용 표현이 포함된다.

따라서 activation은 안전하지만 recall이 불완전하다. 완료된 정책 구현을 이번
작업에서 다시 수정하지 않았으며 운영 활성화 판단은 HOLD다.

## Explicit Feature Satisfaction

분모는 해당 Feature를 명시한 Query의 반환 결과, 분자는 실제
`hard_gate_active_tags`에 Feature가 존재하는 결과다.

| Feature | OFF @5 | ON @5 | Gain | OFF @10 | ON @10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 콘센트있음 | 0% | 0% | 0%p | 0% | 0% |
| 조용함 | 0% | 31.43% | +31.43%p | 0% | 17.14% |
| 노트북작업/작업하기좋음 | 0% | 36.00% | +36.00%p | 0% | 20.00% |
| 혼밥좋음 | 0% | 0% | 0%p | 0% | 0% |
| 분위기좋음 | 0% | 40.00% | +40.00%p | 0% | 20.00% |

Hard Feature 결과는 공통 Hard Gate를 통과한 경우에만 반환되어 위반 0을
유지했다. UNKNOWN은 TRUE로 처리하지 않았다.

## Latency와 outlier

- OFF 평균/median/p95: 2,073.52 / 739.28 / 1,872.87ms.
- Conditional miss 평균/median/p95: 3,072.57 / 1,797.82 / 4,833.10ms.
- Conditional hit 평균/median/p95: 2,510.14 / 1,189.54 / 2,417.04ms.
- 활성 Query miss: embedding 678.20ms, vector 178.93ms, merge 373.25ms.
- 활성 Query hit: embedding 0.12ms, vector 120.28ms, merge 371.01ms.
- skipped Query embedding calls는 0이다.

최대 약 40초 outlier는 `광주 혼밥하기 좋은 식당`이다. 세 variant에서 DB
후보 조회가 38.87--39.17초, Kakao가 0.63--0.66초였다. Semantic embedding과
vector 검색은 이 Query에서 실행되지 않았다. 원인은 external provider가 아니라
기존 DB retrieval이며 안전한 국소 수정이 명확하지 않아 timeout 로직을 바꾸지
않았다.

## 사람 검수

자동 Feature Satisfaction으로 판단하기 어려우면서 OFF/ON 결과가 달라진 4개
Query만 `backend/tmp/semantic_conditional_review_final.csv`에 남겼다. 한 행에서
OFF와 ON Top-5를 비교하며 `preferred_variant`, `relevant_places`, `notes`는
비어 있다. 정답을 자동 입력하지 않았다.

## Tier 2와 Dashboard

기존 scheduler/worker를 유지했다. 오늘 100 places를 처리해 Evidence 44,
active Evidence 2, PlaceTag 2가 증가했다. Naver calls는 111이며 신규 대량
budget을 추가하지 않았다. Dashboard는 운영 JSON document registry와
`ISOLATED_NOT_OPERATING` pgvector staging을 구분하고 flags OFF를 표시한다.

## 운영 pgvector 전환 Runbook

1. 운영 DB의 logical backup과 volume snapshot을 만들고 복원 시험 및 checksum을 기록한다.
2. backup을 운영 volume과 무관한 staging volume에 복원한다.
3. `docker/pgvector-staging/Dockerfile`과 같은 PostgreSQL 16 + PostGIS + pgvector 이미지를 pin한다.
4. staging에서 PostGIS를 확인하고 `CREATE EXTENSION vector`와 512D smoke query를 실행한다.
5. 별도 `PlaceFeatureEmbedding` migration을 staging에만 적용한다.
6. provider/model/dimension/strategy/source-hash가 현재인 embedding만 import한다.
7. row/place duplicate, dimensions, source-hash mismatch가 모두 0인지 확인한다.
8. HNSW `vector_cosine_ops`를 만들고 build time/index size를 기록한 뒤 ANALYZE한다.
9. EXPLAIN ANALYZE와 Top-K 5/10/20/50을 기록하고 OFF/ON safety regression을 실행한다.
10. Dashboard가 staging을 운영 ON으로 표시하지 않는지 확인한다.
11. scheduler/worker/queue가 기존 정책으로 동작하고 Semantic 작업과 분리됐는지 확인한다.
12. rollback은 flags OFF, 앱 vector 경로 제거, 이전 image/volume 또는 검증 backup 복원,
    count/check 재실행 순서로 수행한다. in-place extension downgrade는 하지 않는다.

## 다음 대상과 결정

전체 393,780 Place 중 current active positive Evidence가 있고 accepted status이며
current negative Evidence가 없는 Place는 105,693개다. Feature가 없는 288,087개는
현재 문서에 검색 의미 정보가 거의 없어 embedding 비용보다 품질 이득 근거가
부족하다. 다음 확대 대상은 105,693개 전체가 아니라 10K 제외 eligible Feature
Place를 Category/Region/Feature 희소성과 실제 Query 수요로 다시 층화한 묶음이다.

10K embedding과 staging 저장은 성공했다. 안전성과 일부 Feature Satisfaction도
개선됐지만 activation 누락 16개, 콘센트/혼밥 gain 0, 사람 label 미완료 때문에
운영 pgvector 전환과 Conditional Candidate Injection 운영 ON은 아직 HOLD다.
