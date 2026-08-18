# 관리자 장소 데이터 운영 대시보드

관리자 전용 `/admin/operations` 화면은 Spring이 발급한 공유 JWT를 그대로 사용한다. Django의 `SharedJWTAuthentication`과 DRF `IsAdminUser`가 `User.is_staff`를 검사하므로 프런트 메뉴를 숨기는 것만으로 권한을 대신하지 않는다. 일반 사용자와 비로그인 사용자는 `/api/recommendations/admin/operations/`를 직접 호출해도 거부된다.

## 지표 정의

- 신규 Evidence: 선택 기간에 `PlaceTagEvidence.created_at`이 생성된 행 수다.
- 신규 active Evidence: 선택 기간에 생성됐고 조회 시점에 만료되지 않은 Evidence 수다. stale Evidence를 다시 current로 간주하지 않는다.
- 신규 PlaceTag: 선택 기간에 처음 생성된 `PlaceTag` 수다. 기존 집계 행의 confidence/status 갱신은 포함하지 않는다.
- Evidence Place: 선택 기간에 Evidence가 생성된 distinct Place 수다. 누적 Evidence Place와 다르다.
- Place Coverage: 해당 축 전체 Place 중 active Evidence가 하나 이상 있는 Place 비율이다.
- Tag Coverage: Category profile에서 가능한 `Place × Canonical Tag` pair 중 active positive Evidence pair 비율이다.
- Evidence/API, active/API: Strategy가 만든 신규 Evidence 또는 신규 active Evidence를 Provider 요청 수로 나눈 값이다.
- stale: `expires_at <= now`인 Evidence다. 삭제 수가 아니다.
- conflict: 현재 `PlaceTag.status=needs_verification` 수다.

검색 latency는 현재 요청별로 영속 저장하지 않는다. 정적 benchmark를 운영 수치처럼 표시하지 않고 `NOT_AVAILABLE`로 반환한다. Scheduler/worker 상태도 Docker를 제어하지 않으며 DB의 최근 계획/성공 시각으로 추론한 값임을 명시한다.

Semantic 영역은 운영 JSON FeatureDocument registry의 count와 실제 feature flags를
표시한다. 별도 10K pgvector staging은 `ISOLATED_NOT_OPERATING`으로 표시해 staging
row가 운영 Retrieval/Candidate Injection ON처럼 보이지 않게 한다.

## 집계 성능과 갱신

지역·카테고리 Coverage를 매 API 요청마다 계산하면 대형 DISTINCT/GROUP BY가 반복된다. `OperationsDashboardSnapshot`에 `Region × Category × Tag` Coverage와 공식 Source freshness를 일일 materialization하고, 오늘/7일/30일 성장과 Provider/Queue 지표만 실시간 계산한다.

```bash
python manage.py refresh_operations_dashboard_snapshot
python manage.py report_daily_tag_growth
python manage.py report_daily_tag_growth --days 7 --json
python manage.py report_daily_tag_growth --days 30 --region 부산 --category cafe
```

Scheduler는 당일 queue/processing이 모두 끝났고 마지막 완료 Job이 현재 snapshot보다 새로울 때 한 번만 snapshot을 갱신한다. Evidence와 PlaceTag의 `created_at` 인덱스는 기간 집계의 parallel sequential scan을 방지한다.

## API

`GET /api/recommendations/admin/operations/?days=7&region=부산&category=cafe`

지원 기간은 1/7/30일, 지역은 서울·부산·인천·대구·대전·광주·울산, Category는 cafe/restaurant/toilet/parking/city_park/shelter/library/tourism/freewifi다. 필터는 Backend query와 snapshot dimension에 적용되며 전체 raw row를 브라우저로 보내지 않는다.

## 성장 지표 스냅샷 성능

일일 스냅샷에는 최근 30일 일별 성장량, 1/7/30일 합계와 기간별 active Tag 상위 10개도 저장한다. Region/Category 필터가 없는 요청은 이 값을 재사용하므로 Evidence와 PlaceTag 전체를 매번 다시 스캔하지 않는다. 필터가 있는 요청은 선택한 차원의 정확한 값을 위해 실시간 집계를 유지한다.

2026-08-17 개발 DB에서 스냅샷 갱신은 scheduler의 오프라인 작업으로 약 31.3초가 걸렸다. 스냅샷 갱신 후 서비스 함수의 실측 시간은 1일 약 1.13초, 7일 약 1.75초, 30일 약 1.87초였다.
