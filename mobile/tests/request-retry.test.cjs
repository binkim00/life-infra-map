const assert = require("node:assert/strict");
const test = require("node:test");

const {
  CONNECTION_ERROR_MESSAGE,
  httpErrorMessage,
  isSafeRetryMethod,
  runWithConnectionRetry,
  TIMEOUT_ERROR_MESSAGE,
} = require("../src/api/request-retry.ts");

test("GET 연결 실패는 간격을 늘리며 최대 두 번 재시도한다", async () => {
  const connectionError = new Error("connection");
  let calls = 0;
  const retries = [];

  const result = await runWithConnectionRetry({
    method: "GET",
    retryDelaysMs: [1, 2],
    shouldRetry: (error) => error === connectionError,
    onRetry: (info) => retries.push(info),
    request: async () => {
      calls += 1;
      if (calls < 3) throw connectionError;
      return "ok";
    },
  });

  assert.equal(result, "ok");
  assert.equal(calls, 3);
  assert.deepEqual(
    retries.map(({ attempt, maxAttempts, delayMs }) => ({
      attempt,
      maxAttempts,
      delayMs,
    })),
    [
      { attempt: 2, maxAttempts: 3, delayMs: 1 },
      { attempt: 3, maxAttempts: 3, delayMs: 2 },
    ],
  );
});

test("POST와 PATCH는 연결 실패여도 자동 재전송하지 않는다", async () => {
  for (const method of ["POST", "PATCH"]) {
    let calls = 0;
    await assert.rejects(
      runWithConnectionRetry({
        method,
        retryDelaysMs: [0, 0],
        shouldRetry: () => true,
        request: async () => {
          calls += 1;
          throw new Error("connection");
        },
      }),
    );
    assert.equal(calls, 1);
  }
});

test("HTTP 오류와 타임아웃으로 분류한 실패는 GET에서도 재시도하지 않는다", async () => {
  for (const kind of ["http-400", "http-500", "timeout"]) {
    let calls = 0;
    await assert.rejects(
      runWithConnectionRetry({
        method: "GET",
        retryDelaysMs: [0, 0],
        shouldRetry: (error) => error.kind === "connection",
        request: async () => {
          calls += 1;
          throw { kind };
        },
      }),
    );
    assert.equal(calls, 1);
  }
});

test("재시도 대기 중 사용자가 취소하면 다음 요청을 보내지 않는다", async () => {
  const controller = new AbortController();
  let calls = 0;
  let retries = 0;

  const request = runWithConnectionRetry({
    method: "GET",
    signal: controller.signal,
    retryDelaysMs: [50, 100],
    shouldRetry: () => true,
    onRetry: () => {
      retries += 1;
      controller.abort();
    },
    request: async () => {
      calls += 1;
      throw new Error("connection");
    },
  });

  await assert.rejects(request, (error) => error.name === "AbortError");
  assert.equal(retries, 1);
  assert.equal(calls, 1);
});

test("GET, HEAD, OPTIONS만 안전한 자동 재시도 대상으로 본다", () => {
  assert.equal(isSafeRetryMethod(), true);
  assert.equal(isSafeRetryMethod("get"), true);
  assert.equal(isSafeRetryMethod("HEAD"), true);
  assert.equal(isSafeRetryMethod("OPTIONS"), true);
  assert.equal(isSafeRetryMethod("DELETE"), false);
});

test("연결 실패, 타임아웃, 서버 오류 메시지를 구분하고 내부 정보를 숨긴다", () => {
  assert.notEqual(CONNECTION_ERROR_MESSAGE, TIMEOUT_ERROR_MESSAGE);
  assert.equal(
    httpErrorMessage(400, { detail: "검색어를 입력해 주세요." }),
    "검색어를 입력해 주세요.",
  );

  const unsafeDetail =
    "java.net.UnknownHostException: life-infra-map-db.taile29cc8.ts.net";
  const clientMessage = httpErrorMessage(400, { detail: unsafeDetail });
  const serverMessage = httpErrorMessage(500, { detail: unsafeDetail });
  assert.doesNotMatch(clientMessage, /UnknownHostException|ts\.net/);
  assert.doesNotMatch(serverMessage, /UnknownHostException|ts\.net/);
  assert.match(serverMessage, /서버에서 요청을 처리하지 못했습니다/);
});
