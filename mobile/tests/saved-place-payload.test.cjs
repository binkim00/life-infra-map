const assert = require("node:assert/strict");
const test = require("node:test");
const { savedPlacePayload } = require("../src/utils/saved-place-payload.ts");

const place = { name: "테스트 장소", category: "cafe", address: "부산", lat: 35.1, lng: 129.1 };

test("DB 추천 결과는 실제 DB ID와 서버의 local_db 출처를 보낸다", () => {
  const payload = savedPlacePayload({ ...place, id: "db:42", source: "db", place_id: 42 });
  assert.equal(payload.placeId, 42);
  assert.equal(payload.placeKey, "place:42");
  assert.equal(payload.source, "local_db");
  assert.equal(payload.externalId, "");
});

test("카카오 숫자 ID를 DB 장소 ID로 해석하지 않는다", () => {
  const payload = savedPlacePayload({ ...place, id: 12345, source: "kakao", external_id: "12345" });
  assert.equal(payload.placeId, null);
  assert.equal(payload.source, "kakao");
  assert.equal(payload.externalId, "12345");
  assert.equal(payload.placeKey, "kakao:12345");
});

test("일반 검색 DB 장소와 외부 장소는 각각 올바른 출처로 저장한다", () => {
  const db = savedPlacePayload({ ...place, id: 7, result_source: "db" });
  const external = savedPlacePayload({ ...place, id: "kakao:9", result_source: "kakao", kakao_place_id: "9" });
  assert.equal(db.placeId, 7);
  assert.equal(db.source, "local_db");
  assert.equal(external.placeId, null);
  assert.equal(external.externalId, "9");
  assert.equal(external.source, "kakao");
  assert.equal(db.placeKey, "place:7");
  assert.equal(external.placeKey, "kakao:9");
});

test("DB 결과의 원본 수집 출처보다 검색 결과 출처를 우선한다", () => {
  const payload = savedPlacePayload({ ...place, id: 42, source: "kakao_local", result_source: "db", external_id: "12345" });
  assert.equal(payload.placeId, 42);
  assert.equal(payload.placeKey, "place:42");
  assert.equal(payload.source, "local_db");
});

test("좌표가 없는 웹 후보는 잘못된 숫자를 서버에 보내지 않는다", () => {
  const payload = savedPlacePayload({ ...place, id: "web:1", source: "web", lat: NaN, lng: NaN });
  assert.equal(payload.placeId, null);
  assert.equal(payload.lat, null);
  assert.equal(payload.lng, null);
});
