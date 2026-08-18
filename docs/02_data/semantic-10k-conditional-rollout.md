# Conditional Semantic 10K 결과와 운영 전환 Runbook

기준일은 2026-08-18이다. 기존 Structured Intent 기반 `semantic_required`
구현의 누락 blocker를 일반화했으며, 운영 PostgreSQL에는 pgvector extension이나 vector
migration을 적용하지 않았다. 운영 기본값은 Retrieval OFF, Candidate Injection
OFF, Semantic weight 0.10이다.

## 10K 층화 표본

표본은 random sampling이 아니라 Region, Category, Feature cluster를 순환하는
결정적 층화 방식으로 선택했다. current active positive Evidence가 있고 negative
Evidence가 없는 Canonical Feature만 사용했다.

- Region: 서울 1,822, 부산 1,927, 인천 1,890, 대구 1,558, 대전 1,296,
  광주 615, 울산 892.
- Category: cafe 442, restaurant 3, city_park 500, library 842, parking
  1,295, shelter 1,695, toilet 2,206, tourism 34, freewifi 2,983.
- Feature cluster: work 3,036, solo/social 307, outdoor 585, facility 3,036,
  other 3,036.
- 부족 cell: restaurant 3, tourism 34. 공급 부족을 가짜 데이터로
  보충하지 않았다.
- 같은 범위의 eligible Place는 27,536개이며 표본은 36.32%다. 실제 eligible
  Category는 기존 8개와 `freewifi`이며, `freewifi` eligible Place는 8,279개다.
- 기존 고정 10K 대비 7,017 Place는 유지되고 2,983 Place가 바뀐다.

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

이번 blocker 수정에서는 embedding을 다시 실행하지 않았다. Dynamic sample의
변경 예상 2,983문서는 약 104,703 input tokens, USD 0.00209406, batch 30회다.
이는 dry-run 추정치이며 실제 API 호출과 staging import는 하지 않았다.

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

- semantic_required 48, skipped 2. skipped embedding API calls 0.
- skip은 `부산역 근처 식당`, `부산 주차장` 두 단순 Query뿐이다.
- 결과 변경 15, no-result OFF/ON 모두 9.
- Hard/Category/Region violation 0/0/0.
- duplicate 0, unsupported reason 0.
- 기존 변경 14 Query 중 9개가 변경되고 5개가 동일했다.
- 잘못 활성화된 단순 Region+Category Query는 발견되지 않았다.
- 명확한 의미 Query 누락 16개는 0개로 줄었다. 단순 Query 오활성도 0이다.

원인은 broad clarification과 generic 식당/카페 분기가 Canonical composition보다
먼저 반환하고, 목적형 Feature의 기본 Category가 없던 것이었다. Canonical alias,
semantic intent와 condition 구조를 먼저 합성하도록 일반화했으며 문장 전체를
하드코딩하지 않았다.

## Explicit Feature Satisfaction

분모는 해당 Feature를 명시한 Query의 반환 결과, 분자는 실제
`hard_gate_active_tags`에 Feature가 존재하는 결과다.

| Feature | OFF @5 | ON @5 | Gain | OFF @10 | ON @10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 콘센트있음 | 0% | 0% | 0%p | 0% | 0% |
| 조용함 | 0% | 31.43% | +31.43%p | 0% | 17.14% |
| 노트북작업/작업하기좋음 | 0% | 30.00% | +30.00%p | 0% | 16.67% |
| 혼밥좋음 | 0% | 0% | 0%p | 0% | 0% |
| 분위기좋음 | 0% | 20.00% | +20.00%p | 0% | 10.00% |
| 혼자이용좋음 | 0% | 0% | 0%p | 0% | 0% |
| 데이트좋음 | 0% | 33.33% | +33.33%p | 0% | 16.67% |
| 대화하기좋음 | 0% | 0% | 0%p | 0% | 0% |
| 장기체류좋음 | 0% | 0% | 0%p | 0% | 0% |
| 잠깐쉬기좋음 | 0% | 0% | 0%p | 0% | 0% |

Hard Feature 결과는 공통 Hard Gate를 통과한 경우에만 반환되어 위반 0을
유지했다. UNKNOWN은 TRUE로 처리하지 않았다.

## Latency와 outlier

- OFF 평균/median/p95/max: 1,201.19 / 1,010.50 / 2,122.39 / 3,383.22ms.
- Conditional miss 평균/median/p95/max: 2,451.65 / 2,151.45 / 3,831.05 / 6,803.05ms.
- Conditional hit 평균/median/p95/max: 1,571.41 / 1,416.76 / 2,486.43 / 3,064.66ms.
- 활성 Query miss: embedding 평균 703.78ms, vector 평균 156.58ms.
- 활성 Query hit: embedding 평균 0.13ms, vector 평균 88.85ms.
- skipped Query embedding calls는 0이다.

변경 전 `광주 혼밥하기 좋은 식당` collector는 50,911ms였다. EXPLAIN은 KNN
GiST가 반경 내 식당 3개로 LIMIT 150을 채우지 못해 393,777행을 filter에서
제거하고 36,826ms를 사용한 것을 보였다. 직접 Category 검색은 bounded count와
Category 밀도에 따라 dense cell은 KNN, sparse cell/category는 indexed 좌표
Top-N 후 Place fetch를 사용한다. 대표 재측정은 광주 혼밥 713ms, 서울 혼밥
338ms, 부산 혼밥 198ms, 대구 혼밥 75ms, 광주 분위기 식당 83ms, 서울 공원
439ms이며 결과 수와 Category 안전성을 유지했다. 새 인덱스 migration은 없다.

## 사람 검수

자동 Feature Satisfaction으로 판단하기 어려우면서 OFF/ON 결과가 달라진 4개
Query만 `backend/tmp/semantic_conditional_review_final.csv`에 남겼다. 한 행에서
OFF와 ON Top-5를 비교하며 `preferred_variant`, `relevant_places`, `notes`는
비어 있다. 정답을 자동 입력하지 않았다.

## Tier 2와 Dashboard

기존 scheduler/worker는 각각 21시간 이상 실행 중이다. 오늘 Evidence 44,
누적 current active positive Evidence 139,133, PlaceTag 706,811이다. 신규 대량
Naver budget은 추가하지 않았다. Dashboard는 운영 JSON document registry와
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
현재 7개 Region Dynamic 정책의 eligible은 27,536개이고, 다음 직접 후보군은
기존 Dynamic 10K를 제외한 17,536개다.

10K embedding과 staging 저장은 성공했고 activation 누락 및 39초 DB blocker는
해결됐다. 안전성과 조용함/작업/분위기/데이트 Satisfaction도 개선됐지만
콘센트/혼밥/혼자이용/대화/장기체류 gain은 0이며 사람 label 4개가 미완료다.
따라서 운영 pgvector 전환 준비는 가능하지만 Conditional Candidate Injection
운영 ON은 사람 검수와 0-gain Feature 판단이 끝날 때까지 HOLD다.
