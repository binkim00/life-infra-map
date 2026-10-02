const assert = require("node:assert/strict");
const test = require("node:test");
const { tierDisplay, tierColor, authorTierDisplay } = require("../src/utils/tier-display.ts");
const {
  placeReportStatusLabel,
  placeReportTypeLabel,
} = require("../src/utils/place-report-labels.ts");

test("MY 등급은 서버의 현재 등급과 기여도를 표시한다", () => {
  assert.deepEqual(tierDisplay({ tier: "silver", tier_label: "실버", contribution: 120 }), {
    label: "실버", contribution: 120,
  });
  assert.deepEqual(tierDisplay({ tier: "iron", score: 0 }), {
    label: "아이언", contribution: 0,
  });
  assert.deepEqual(tierDisplay(null), { label: "등급 확인 중", contribution: null });
});

test("제보 유형과 상태의 서버 코드를 사용자 문구로 바꾼다", () => {
  assert.equal(placeReportTypeLabel("wrong_info"), "잘못된 정보");
  assert.equal(placeReportTypeLabel("new_place"), "새 장소");
  assert.equal(placeReportTypeLabel("new_code"), "기타 제보");
  assert.equal(placeReportStatusLabel("pending"), "검토 대기");
  assert.equal(placeReportStatusLabel("new_status"), "상태 확인 중");
});

test("MY와 작성자 등급은 같은 서버 색상을 사용하고 잘못된 색상은 노출하지 않는다", () => {
  assert.equal(tierColor({ tier: { tier: "bronze", tier_color: "#B7791F" } }), "#b7791f");
  assert.deepEqual(authorTierDisplay({ author_tier: "bronze", author_tier_label: "이전 문구", author_nickname_color: "#B7791F" }), { label: "브론즈", color: "#b7791f" });
  assert.equal(tierColor({ tier: "iron", tier_color: "tier_color" }), "#8b8b8b");
});
