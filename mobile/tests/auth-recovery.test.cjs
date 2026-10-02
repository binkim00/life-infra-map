const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function harness(fetchImpl, fastTimeout = false) {
  const secrets = new Map();
  const storage = new Map();
  const output = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(require.resolve('../src/api/client.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mockRequire = (name) => {
    if (name === '@react-native-async-storage/async-storage') return {
      getItem: async (key) => storage.get(key) || null,
      setItem: async (key, value) => storage.set(key, value),
      removeItem: async (key) => storage.delete(key),
    };
    if (name === 'expo-secure-store') return {
      getItemAsync: async (key) => secrets.get(key) || null,
      setItemAsync: async (key, value) => secrets.set(key, value),
      deleteItemAsync: async (key) => secrets.delete(key),
    };
    if (name === 'react-native') return { Platform: { OS: 'android' } };
    if (name === 'expo/fetch') return { fetch: fetchImpl };
    if (name === './request-retry') return require('../src/api/request-retry.ts');
    throw new Error(name);
  };
  vm.runInNewContext(code, {
    exports: output.exports, require: mockRequire, process: { env: {} },
    fetch: fetchImpl, AbortController, FormData, URLSearchParams, Headers,
    setTimeout: (fn, ms) => setTimeout(fn, fastTimeout ? 5 : ms), clearTimeout,
  });
  return output.exports;
}

const response = (status, data) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json' },
});

test('인증 갱신 서버 오류는 세션을 지우지 않고 재시도 가능한 오류로 반환한다', async () => {
  const api = harness(async (url) => String(url).endsWith('/auth/refresh')
    ? response(503, {}) : response(401, {}));
  await api.authStorage.write('expired', { id: 1 }, 'refresh');
  await assert.rejects(api.apiRequest('/accounts/me'), (e) => e.status === 503 && e.kind === 'server');
  assert.equal((await api.authStorage.read()).refreshToken, 'refresh');
});

test('인증 갱신 시간 초과는 대기를 끝내고 세션을 보존한다', async () => {
  const api = harness(async (url, options) => {
    if (!String(url).endsWith('/auth/refresh')) return response(401, {});
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted'))));
  }, true);
  await api.authStorage.write('expired', { id: 1 }, 'refresh');
  await assert.rejects(api.apiRequest('/accounts/me'), (e) => e.status === 408 && e.kind === 'timeout');
  assert.equal((await api.authStorage.read()).refreshToken, 'refresh');
});

test('만료된 갱신 토큰은 세션을 비우고 로그인 필요 오류를 반환한다', async () => {
  const api = harness(async () => response(401, {}));
  await api.authStorage.write('expired', { id: 1 }, 'expired-refresh');
  await assert.rejects(api.apiRequest('/accounts/me'), (e) => e.status === 401);
  assert.equal((await api.authStorage.read()).token, null);
});

test('인증 갱신 성공 뒤 새 토큰으로 요청을 완료한다', async () => {
  let calls = 0;
  const api = harness(async (url) => {
    if (String(url).endsWith('/auth/refresh')) return response(200, { access_token: 'new', refresh_token: 'new-refresh' });
    return ++calls === 1 ? response(401, {}) : response(200, { ok: true });
  });
  await api.authStorage.write('expired', { id: 1 }, 'refresh');
  assert.equal((await api.apiRequest('/accounts/me')).ok, true);
  assert.equal((await api.authStorage.read()).token, 'new');
});

test('느린 조회는 시간 초과로 끝나고 다음 재시도는 정상 결과를 받는다', async () => {
  let slow = true;
  const api = harness(async (url, options) => {
    if (!slow) return response(200, { results: [1] });
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted'))));
  }, true);
  await assert.rejects(api.apiRequest('/recommendations/map-search/', { auth: false }),
    (e) => e.status === 408 && e.kind === 'timeout');
  slow = false;
  assert.deepEqual(Array.from((await api.apiRequest('/recommendations/map-search/', { auth: false })).results), [1]);
});

test('서버 오류는 내부 내용을 숨기며 작성 요청을 자동 중복 전송하지 않는다', async () => {
  let calls = 0;
  const api = harness(async () => { calls++; return response(500, { detail: 'java.internal.Exception' }); });
  await assert.rejects(api.apiRequest('/recommendations/place-reports/', { method: 'POST', body: {} }),
    (e) => e.status === 500 && !e.message.includes('Exception'));
  assert.equal(calls, 1);
});
