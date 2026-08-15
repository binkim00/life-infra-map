# 전국 의미 태그 자동 수집

이 파이프라인은 서비스 사용자의 검증에 의존하지 않고 출시 전 의미 태그 근거를 매일 수집한다.
장소 분류나 업종은 의미 태그 수에 포함하지 않는다.

## 구성

- `PlaceTagCollectionJob`: 장소 하나의 당일 복수 의미 태그 수집 작업
- `ProviderQuotaUsage`: 공급자별 일일 예약·실제 호출량 원장
- `plan_daily_tag_collection`: 17개 시도와 장소 유형을 순환해 당일 작업 생성
- `process_place_tag_collection_jobs`: PostgreSQL 잠금으로 작업을 안전하게 선점하는 worker
- `recover_tag_collection_jobs`: 중단된 worker의 작업과 예약 쿼터 복구
- `run_tag_collection_scheduler`: 매일 계획 생성과 복구를 반복하는 상시 scheduler

한 장소에서 태그별로 검색하지 않고 장소 유형별 의미 묶음을 검색한다. 한 문서에서 여러 태그의
긍정·부정 근거를 추출하며, URL이 없는 결과나 장소 동일성이 부족한 결과는 저장하지 않는다.

## 안전장치

- 기본 일일 한도 25,000회 중 90%만 자동 작업에 사용
- 장소·공급자·날짜별 작업 중복 방지
- `SELECT FOR UPDATE SKIP LOCKED` 기반 다중 worker 안전 선점
- 30분 이상 멈춘 작업 자동 회수
- 실패는 최대 3회 지수 재시도
- 근거 없음은 실패가 아니라 완료로 기록
- 웹 근거는 candidate만 만들고 자동 confirmed 금지

## 실행

마이그레이션 후 Docker 프로필을 명시적으로 활성화한다.

```powershell
cd backend
.\venv\Scripts\python.exe manage.py migrate
cd ..
docker compose --profile tag-collection up -d --build tag_scheduler tag_worker
```

상태 확인:

```powershell
docker compose --profile tag-collection ps
docker compose logs --tail 100 tag_scheduler tag_worker
```

중지:

```powershell
docker compose --profile tag-collection stop tag_scheduler tag_worker
```

로컬 PC와 Docker Desktop이 꺼지면 수집도 멈춘다. 실제 운영에서는 같은 두 컨테이너를 항상 켜진
서버에서 실행해야 하며, `restart: unless-stopped`가 프로세스 장애와 서버 재부팅 후 재시작을 담당한다.

## 초기 운영값

처음에는 `TAG_COLLECTION_DAILY_PLACE_LIMIT=100`으로 24시간 검증한다. 장소 매칭률, 장소당 의미
태그 수, 근거 없음 비율과 태그별 precision을 확인한 뒤 500, 2,000, 7,500 순서로 올린다. 검색
호출량은 `ProviderQuotaUsage`에서 확인한다.

## Bootstrap과 Balanced 계획

`plan_daily_tag_collection --mode bootstrap`은 출시 전 밀도 확보용이다. 서울·부산(Tier 1),
광역시(Tier 2), 수원·용인·고양·성남·창원(Tier 3), 그 외 전국(Tier 4)을 기본
`70,15,10,5` 비중으로 뽑는다. 이 비중은 `TAG_COLLECTION_BOOTSTRAP_TIER_WEIGHTS`로 바꿀 수
있으며 포함/제외 조건이 아니다. 장소별 우선순위는 다음 항목의 합이다.

    지역(30/20/12/5)
    + 카테고리 설정값
    + 미확보 관련 태그 수 × 3 (최대 30)
    + 활성 Evidence 없음(20)
    + 최신성 부족(최대 15)
    + 충돌(건당 8, 최대 20)
    + 검색 수요(최대 20)
    + 데이터 품질 부족(최대 10)

`--mode balanced`는 17개 시도를 순환해 장기 전국 Coverage와 refresh 균형을 유지한다.
두 모드 모두 당일 목표보다 Job이 적으면 부족분만 보충하며, 같은 장소·공급자·날짜 Job은
DB 제약으로 중복되지 않는다. 만료 Evidence가 있는 장소는 일반 90일 재방문 제한보다 먼저
refresh 후보가 된다.

현재 직접 Profile은 `cafe`, `restaurant`, `tourism`, `city_park`, `library`, `beach`,
`parking`, `toilet`, `shelter`이다. 이 목록은 최종 범위가 아니라 의미 Feature를 정의한 시작점이다.

## Source와 Canonical Tag 정책

원천 문자열은 `tag_source_policy.py`에서 한 번만 정의한다. 원본 Evidence는
`naver_blog_search`, `web_search`, `field_rule`, `external_data`, `external_api`,
`user_feedback`, `admin_review`로 구분한다. `PlaceTag.source=web_evidence`는 개별 Provider가
아니라 웹 Evidence 집계 결과라는 뜻이다. 과거 `ai_suggested`, `blog_search`, `naver_search`도
재집계를 위해 읽되 신규 저장에는 사용하지 않는다.

AI와 외부 문구는 `canonical_tag_policy.py`의 허용 태그/alias에만 매핑된다. 자유 Tag 생성은
금지한다. 현재 11개 주관 태그에 장기체류, 가족동반, 산책, 야외활동, 휠체어 접근,
장애인 시설/주차, 24시간 운영, 무료 이용, 관리 상태를 점진적으로 추가했다. 카페·식당 같은
장소 분류와 업종은 의미 Tag로 만들지 않는다.

## Identity와 Confidence

Kakao ID 존재 여부는 Evidence 연결 조건이 아니다. `naver_tag_evidence_provider.py`의
`identity_assessment`가 장소명 exact 50점/all terms 40점/partial 20점, 주소 일치 최대 35점
(일부 주소 신호 최소 15점), 강한 지점명 일치 25점을 합산하고 65점 이상만 동일 장소로 본다.
따라서 TourAPI·공공데이터 Place도 이름과 주소가 충분히 맞으면 처리된다.

개별 Evidence confidence는 `evidence_scoring.py`의 설명 가능한 공식으로 계산한다.

    identity × 0.45
    + source trust × 0.20
    + 표현 명확성 × 0.20
    + freshness × 0.15

결과는 25~95로 제한한다. Naver source trust는 65, 공식 field는 95이며 LLM이 스스로 제시한
confidence는 최종 점수로 쓰지 않는다.

웹 Aggregate confidence는 `tag_evidence_aggregation.py`에서 독립 URL 수, positive/negative 수,
source 다양성, 평균 Evidence confidence와 freshness로 계산한다. 예를 들어 candidate는
`25 + positive×8 - negative×7 + 평균×0.25 + source다양성×2 + freshness×0.08`이며 35~75로
제한한다.

## 상태와 UNKNOWN 정책

- 공식 positive는 `confirmed`, 공식 negative는 `rejected`이며 공식 negative가 웹 positive보다 우선한다.
- 관리자 positive 우세 + 웹 positive, 또는 사용자 positive 우세 + 독립 웹 3건이면 `confirmed`할 수 있다.
- 독립 웹 positive 2건 이상이고 순 positive가 2 이상이면 `candidate`다.
- 웹 negative 3건 이상이고 순 negative가 2 이상이면 `rejected`다.
- 한쪽 근거가 약하거나 positive/negative가 충돌하면 `needs_verification`이다.
- 활성 Evidence가 없으면 아무 사실도 materialize하지 않는다. 이는 FALSE가 아니라 UNKNOWN이다.
- 웹 Evidence만으로는 어떤 경우에도 `confirmed`하지 않는다.

공식 negative가 뒤늦게 들어오면 기존 웹 aggregate를 삭제하지 않고 `rejected`로 갱신한다.
원본 `PlaceTagEvidence`와 기존 candidate Seed를 일괄 삭제하지 않는다.

## Freshness, 제한 및 실패 분석

웹 Evidence TTL은 기본 120일이다. 웨이팅은 45일, 노트북/콘센트/와이파이/작업은 180일,
전망은 365일이며 공식/구조화 Evidence는 만료하지 않는다. 만료 행은 삭제하지 않고 refresh
우선순위와 stale 지표에 사용한다.

Provider RPS는 `TAG_COLLECTION_NAVER_RPS`(기본 10)와
`TAG_COLLECTION_DEFAULT_RPS`로 조절한다. 429는 `rate_limited_count`에 기록하고 기존 retry/backoff
경로로 보낸다. 공급자 장애가 다른 Job을 영구 중단시키지 않는다.

Evidence 미확보는 `NO_SEARCH_RESULT`, `IDENTITY_MISMATCH`, `NO_TAG_EXPRESSION`,
`INSUFFICIENT_SNIPPET`, `QUERY_QUALITY`, `OTHER`로 분류해 `report_tag_collection_quality`에서
집계한다. 실패가 아니라 Coverage 개선 입력이다.

## 선택적 AI와 공식 근거

Worker는 먼저 `generate_meaningful_tags`를 호출해 `Place.raw`의 공식/구조화 필드를 Evidence로
만든 다음 웹을 조회한다. Rule extractor가 1차이며, identity가 검증된 실제 snippet에서 Rule이
아무 태그도 찾지 못하고 Job priority가 기준 이상일 때만 선택적 AI extractor가 동작한다.
AI는 허용 Canonical Tag, polarity, 입력에 실제로 존재하는 evidence span만 반환할 수 있다.
현재 기본값 `TAG_COLLECTION_AI_EXTRACTOR_ENABLED=false`이므로 비용 검증 전 자동 호출하지 않는다.

## Coverage와 출시 준비 판정

`report_bootstrap_readiness`는 Region × Category × Tag별 Evidence coverage, 상태, conflict, stale,
UNKNOWN, source diversity를 출력한다. 도시 판정 기본값은 Evidence 장소 20%, Tag pair 10%,
high-confidence 40% 이상, conflict 10% 이하, stale 40% 이하다. 각각 다음 환경변수로 조정한다.

- `TAG_COLLECTION_READY_EVIDENCE_COVERAGE`
- `TAG_COLLECTION_READY_TAG_COVERAGE`
- `TAG_COLLECTION_READY_HIGH_CONFIDENCE`
- `TAG_COLLECTION_READY_MAX_CONFLICT`
- `TAG_COLLECTION_READY_MAX_STALE`

검수는 `export_manual_review_priority`로 conflict, hard constraint, 중간 confidence, 단일 Evidence 등
영향도가 큰 행만 우선한다. 전체 Place를 사람이 검수하는 구조가 아니다.

## 2026-08-16 실제 Bootstrap 관측

- 기존 balanced 100곳: Evidence Place 16곳(16%), 웹 Evidence 40건
- 수정 후 혼합 bootstrap 100곳: Evidence Place 20곳(20%), 웹 Evidence 40건, 구조화 Evidence 17건
- 후속 category-heavy 100곳: Evidence Place 12곳(12%), 웹 Evidence 35건, 구조화 Evidence 24건
- 처리량 확장 500곳: Evidence Place 43곳(8.6%), 웹 Evidence 68건, 구조화 Evidence 103건,
  Naver 1,039회, 207.9초, 실패/429 0
- 세 배치 모두 API 실패 0, 429 0, 선택적 AI 호출 0
- 활성 Evidence pair의 `PlaceTag` materialization은 source mismatch 수정 후 100%

확장 실행까지 당일 총 900 Job, Naver 2,128회가 모두 완료됐다. 최종 활성 Evidence pair 185개는
공식 confirmed 144개와 웹 aggregate 41개(candidate 1, needs_verification 40)로 모두 materialize됐다.
활성 positive/negative 충돌은 1 pair다. 500곳 hit rate가 낮은 주원인은 공원 200곳과 관광지
88곳 등 블로그 근거 적합도가 낮은 카테고리 비중이 커졌기 때문이다.

전체 hit rate가 일관되게 상승했다고 보기는 아직 어렵다. 카페는 후속 배치에서 23곳 중 11곳이
성공했지만 공원·화장실 같은 공공시설은 블로그 snippet coverage가 낮다. 현재 가장 큰 병목은
`IDENTITY_MISMATCH`와 카테고리별 source 적합성이다. 따라서 새 유료 Provider를 바로 추가하기보다
공식 구조화 데이터 연결과 카테고리별 query/identity 정책을 먼저 확장한다.

## 2026-08-16 공공시설 Structured Evidence backfill

화장실 최종 DB-ready 파일은 이름·주소·좌표만 남겨 원본의 36개 공식 필드를 유실하고 있었다.
`backfill_public_facility_raw`는 `ExData/Cleaned/toilet_places.json`의 동일 `external_id`를 기존
`public_toilet_standard` Place에 연결하고, 기존 raw를 바꾸지 않은 채 누락 필드만
`official_backfill` namespace에 추가한다. 주차장과 도시공원은 기존 중첩 raw에 공식 필드가
이미 있어 복제하지 않는다. 향후 화장실 재import 때는 `import_fixture_places`가 정제 원본을
fallback으로 결합해 같은 유실을 방지한다.

    python manage.py backfill_public_facility_raw --category toilet --region 서울특별시 --limit 100 --dry-run
    python manage.py backfill_public_facility_raw --dry-run
    python manage.py backfill_public_facility_raw
    python manage.py report_structured_evidence_coverage --output tmp/structured_evidence_coverage.json

45,065개 원본 중 기존 Place 45,060개가 source ID로 연결됐고, 화장실 29,127곳에 공식 raw가
보강됐다. 원본 `데이터기준일자`가 있는 Place는 `source_updated_at`에도 저장하고 Evidence의
`observed_at`으로 사용한다. 공식 원문에서 직접 확인되는 경우에만 다음 태그를 만든다.

- 화장실: 장애인용 변기 수가 1개 이상이면 `장애인시설`, 24시간/상시 명시가 있으면 `24시간운영`
- 주차장: 무료 명시 `무료이용`, 장애인 전용구역 보유 명시 `장애인전용주차`, 모든 운영일의
  00:00~23:59/24:00 명시 `24시간운영`
- 도시공원: 해당 시설 문자열이 실제 존재할 때만 `놀이시설`, `운동시설`, `편의시설`

공식 Evidence는 144건에서 47,900건으로 증가했다. `PlaceTagEvidence` 전체는 400건에서
48,156건, Evidence 보유 Place는 207곳에서 32,174곳으로 증가했다. 원본에 없는 값이나
카테고리만으로 추론한 태그는 만들지 않는다.

사람 검수용 `identity_evidence_validation_final_150.csv`는 accepted 75행/rejected 75행이며,
정답 열은 비어 있다. 다음 명령은 사람이 입력한 O/X/애매 값만 읽고 CSV를 수정하지 않는다.

    python manage.py analyze_evidence_validation tmp/identity_evidence_validation_final_150.csv

Identity, Evidence relevance, Tag, polarity 지표를 전체·Category·Source·confidence 구간별로
출력하며 미입력과 애매 판정은 precision 분모에서 제외한다.
