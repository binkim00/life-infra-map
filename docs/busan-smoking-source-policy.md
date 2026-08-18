# 부산 흡연 관련 장소 수집 정책

## 데이터 의미

공식 여부는 DB 저장 조건이 아니다. 웹에서 발견한 장소도 장소 Identity, 지도에서 사용할 수 있는 위치, 출처 Evidence가 충분하면 `Place`로 저장한다. 대신 Source, confidence, freshness, verification을 보존하고 `WEB_VERIFIED` 또는 `UNVERIFIED`로 사용자에게 확인 수준을 표시한다.

- `designated_smoking_area`: 최신 공식 자료가 지정 흡연구역이라고 명시한 장소
- `smoking_booth`, `smoking_room`: 부스 또는 실의 현행 운영이 확인된 장소
- `ashtray_only`: 재떨이 설치만 확인된 장소. `smoking_permission=unknown`을 고정한다.
- `smoking_area_candidate`: 웹에서 흡연 위치로 안내되지만 공식 현행 확인이 부족한 장소. `smoking_permission=unverified`로 둔다.

재떨이는 흡연 허용을 뜻하지 않는다. UI에는 다음 안내를 함께 표시한다.

> 재떨이 설치가 확인된 위치입니다. 공식 지정 흡연구역 여부는 확인되지 않았으므로 현장 안내와 관련 규정을 확인해 주세요.

## 좌표와 현장 위치 안내

좌표와 위치 설명은 별개로 관리한다. `Place.detail_location`은 사용자가 현장에서 찾을 수 있는 원문 기반 위치 설명을 담고, `Place.raw`와 Evidence context에는 `location_description`, `location_landmark`, `location_directions`, `location_accuracy`, `location_source_url`, `location_evidence_span`을 보존한다.

정확도는 `EXACT`, `ENTRANCE`, `BUILDING`, `LANDMARK`, `APPROXIMATE`, `UNKNOWN`을 사용한다. 출구나 건물 좌표는 흡연 설비 자체 좌표라고 표현하지 않는다. Source가 “인근”까지만 말하면 방향이나 거리를 새로 만들지 않고 그 수준의 설명만 반환한다.

## 상태와 근거

`VERIFIED_OFFICIAL`은 최신 지자체·공공기관·시설 운영자의 현행 위치 자료가 있고 장소 식별이 명확할 때만 사용한다. 설치 계약은 준공을 뜻하지 않으므로 `NEEDS_VERIFICATION`이다. 단일 비공식 문서, 오래된 설치 기사, 폐쇄 신고가 있는 자료는 각각 `NEEDS_VERIFICATION`, `STALE`, `POSSIBLY_REMOVED`로 유지한다.

근거에는 URL, 제목, 출처 유형, 발행일, 수집일, 짧은 근거 문장만 보존한다. 지도 리뷰 원문은 수집하지 않는다. 공식 근거 또는 프로젝트가 허용한 지오코딩 결과가 없으면 좌표를 만들지 않는다.

## 검색 노출 순서

1. 검증된 공식 지정 흡연구역
2. 검증된 흡연부스·흡연실
3. `HIGH_CONFIDENCE_WEB`
4. `ASHTRAY_ONLY`
5. `NEEDS_VERIFICATION`

3~5단계는 상태 배지와 주의 문구를 반드시 노출한다. 후보를 법적으로 흡연 가능한 장소라고 표현하지 않는다.

`verification_level`은 저장 컬럼이 아니라 Place 원본, PlaceTag, PlaceTagEvidence에서 계산한다. 값은 `VERIFIED`, `PUBLIC_DATA`, `WEB_VERIFIED`, `UNVERIFIED`, `ASHTRAY_ONLY`, `STALE`이다. 공공데이터의 흡연실 여부처럼 원본 필드가 명시적인 레코드는 `PUBLIC_DATA`로 검색할 수 있지만 독립 현행 검증과 구분한다.

## 지도 및 자연어 검색

지도 조회는 기존 `GET /api/recommendations/places/`를 사용한다. `category=smoking_area`와 `min_lat`, `min_lng`, `max_lat`, `max_lng`를 함께 보내 현재 화면 범위만 조회한다. 선택적으로 `facility_type`, 쉼표 구분 `verification`, `include_stale`를 보낼 수 있다. 기본값은 stale·철거 가능 항목을 숨긴다. 응답의 `smoking` 객체는 시설 유형, permission, verification level, 마지막 확인일, confidence, source summary를 제공한다.

읽기 단계에서는 동일 정규화 이름과 약 100m 좌표 격자를 묶고 `duplicate_count`를 반환한다. DB 레코드는 병합하거나 삭제하지 않는다.

자연어 별칭은 흡연구역·흡연장소·흡연실·흡연부스·담배 피울 곳·담배필곳·재떨이를 `smoking_area`로 연결한다. 재떨이는 `facility_type=ashtray_only`, “공식” 요청은 `verification=VERIFIED_OFFICIAL`이라는 hard filter 힌트를 검색 계획에 남긴다.

## 최신성 및 전국 확장

각 근거는 `published_at`, `retrieved_at`, `last_verified_at`, 출처 수와 철거·폐쇄 신호를 가진다. 정기 작업은 공식 원본 갱신, 시설 중심 검색, 폐쇄 신호 검색, 기존 Place 중복 비교, 사람이 검수하는 candidate 승격 순으로 실행한다. 도시·구군·시설 목록과 검색어만 설정으로 분리하면 같은 dry-run 수집기를 전국에 재사용할 수 있다.
