const assert = require("node:assert/strict");
const test = require("node:test");
const { isNotificationVisible } = require("../src/utils/notification-visibility.ts");

test("댓글·문의 답변 숨김 설정은 해당 종류의 알림 목록에만 적용된다", () => {
  const settings = { commentNotifications: false, inquiryNotifications: false };
  assert.equal(isNotificationVisible("post_commented", settings), false);
  assert.equal(isNotificationVisible("inquiry_answered", settings), false);
  assert.equal(isNotificationVisible("tier_upgraded", settings), true);
  assert.equal(isNotificationVisible("system", settings), true);
});
