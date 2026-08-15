# Evidence 확보율 병목 분석 (2026-08-16)

## 기준선

동일 최신 500 Job의 기존 결과는 웹 Evidence 43곳(8.6%), `IDENTITY_MISMATCH` 314,
`NO_SEARCH_RESULT` 71, `NO_TAG_EXPRESSION` 72였다. 공식 `field_rule`까지 포함하면 Evidence 보유
Place는 103곳(20.6%)이다. 기존 리포트의 8.6%는 웹 Hit만 센 값이므로 두 지표를 분리해야 한다.

## 실제 mismatch 314건

`analyze_identity_mismatches`로 같은 Place를 재검색해 DB에 원문을 저장하지 않고 짧은 제목,
snippet, URL과 판정 신호만 분석했다. Naver 642회, 실패 0이었다.

| 원인 | 건수 | 비율 |
|---|---:|---:|
| NAME_MISMATCH | 227 | 72.3% |
| WRONG_SEARCH_RESULT | 32 | 10.2% |
| REGION_MISMATCH | 20 | 6.4% |
| IDENTITY_THRESHOLD | 15 | 4.8% |
| BRANCH_NAME_MISMATCH | 13 | 4.1% |
| INSUFFICIENT_IDENTITY_INFO | 6 | 1.9% |
| 재검색 시 정상 match | 1 | 0.3% |

`NAME_MISMATCH`의 대부분은 같은 시·구 표현만 있고 장소명이 없는 결과다. 공원·화장실·주차장
같은 일반명은 지역이 같다는 이유로 연결하면 안 된다. `IDENTITY_THRESHOLD`에도 실제 관광지
정식 명칭과 `꽃동네`, `그런고로`, `성곽` 같은 우연한 일반 문구가 섞여 있어 exact name 전체를
완화하는 방식은 채택하지 않았다.

## 채택한 Identity 변경

- 주소에 명시된 시도와 검색 결과의 명시 시도가 다르면 제목 일치 보너스가 있어도 차단한다.
- 5자 이상 정식 명칭이 제목에 직접 나온 경우만 제한적으로 15점을 보강한다.
- TourAPI는 정식 명칭+동일 지역, 또는 복수의 고유 명칭 term+동일 지역일 때만 보강한다.
- `화장실`, `주차장`, `공원`, `전망대` 같은 category 일반어는 복수 고유 term으로 세지 않는다.
- 관광지/공원의 `주차 웨이팅 없음`은 장소 자체의 `웨이팅적음` Evidence로 추출하지 않는다.

검색어에 `공원`, `공중화장실`, `주차장`을 일괄 추가하는 실험은 Hit 30/500,
`IDENTITY_MISMATCH` 323으로 악화되어 코드에서 제거했다.

## 동일 500곳 최종 재검증

| 지표 | 변경 전 | 최종 안전 규칙 |
|---|---:|---:|
| 웹 Evidence Place | 43 | 45 |
| 웹 Hit Rate | 8.6% | 9.0% |
| Identity 통과 Place | 115 | 128 |
| IDENTITY_MISMATCH | 314 | 301 |
| NO_SEARCH_RESULT | 71 | 71 |
| NO_TAG_EXPRESSION | 72 | 83 |
| API 요청 | 1,039 | 1,039 |
| API 실패 / 429 | 0 / 0 | 0 / 0 |
| 실행 시간 | 207.9초(기존 worker batch) | 461.5초(직렬 재검증) |

Identity에서 13곳을 더 살렸지만 그중 상당수는 의미 표현이 없어 `NO_TAG_EXPRESSION`으로
이동했다. 즉 threshold 완화로 Hit를 부풀리지 않았다. 실험 과정에서 신규 Evidence 3건이
생겼고 최종 안전 실행에서는 추가 신규 행과 PlaceTag가 0건이었다. 기존 Evidence 삭제 금지
원칙에 따라 실험 중 생성 행은 삭제하지 않고 검수 CSV에 포함했다.

## Category별 Source 결론

- cafe/restaurant: 현재 보유 구조화 속성이 빈약하므로 Naver Blog가 주관 태그의 주 Source다.
- tourism: TourAPI `Place.raw`와 상세 공식 field 우선, Blog는 분위기·데이트·전망 보강용이다.
- city_park: 도시공원 표준데이터의 시설 field와 `field_rule` 우선, Blog는 보조다.
- parking: 표준데이터의 요금·운영시간·장애인주차 field가 Blog보다 강하다.
- toilet: 현재 `Place.raw`가 이름·주소·좌표 위주라 원본 어댑터에서 접근성/운영/시설 field를
  보존하는 개선이 먼저다. Blog는 동일 시설 확인이 어려워 최후 순위다.
- shelter: heat shelter 원본 운영시간/실내·시설 field가 우선이며 Blog는 적합도가 낮다.
- library/beach: 공식 표준/공식 지자체 정보 우선, Blog는 주관 속성만 보강한다.

세부 DB 수치는 `report_category_evidence_sources` 결과로 확인한다.

## 사람 검수

`export_identity_evidence_validation_set`이 150행 CSV를 만든다. 최종 파일은 실제 저장 Evidence
75행과 탈락 Identity 75행으로 구성된다. `identity_correct`, `evidence_about_place`,
`tag_supported`, `polarity_correct`, `review_notes`는 비워 두며 사람이 직접 입력한다. 자동
precision은 만들지 않는다.
