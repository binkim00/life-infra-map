const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

test("초안은 재실행 후 복원되고 계정별로 분리되며 제출 뒤 이전 저장이 되살아나지 않는다", async () => {
  const rows = new Map();
  const storage = {
    getItem: async key => rows.get(key) || null,
    setItem: async (key, value) => { rows.set(key, value); },
    removeItem: async key => { rows.delete(key); },
  };
  let owner = 1476;
  function mount() {
    const slots = [];
    let index = 0;
    let effects = [];
    const react = {
      useRef(value) { const n = index++; return slots[n] ||= { current: value }; },
      useState(value) {
        const n = index++;
        if (!(n in slots)) slots[n] = value;
        return [slots[n], value => { slots[n] = value; }];
      },
      useCallback(fn) { index++; return fn; },
      useEffect(fn, deps) {
        const n = index++;
        if (!slots[n] || deps.some((v, i) => v !== slots[n].deps[i])) {
          slots[n]?.cleanup?.();
          effects.push(() => { slots[n] = { deps, cleanup: fn() }; });
        }
      },
    };
    const source = ts.transpileModule(fs.readFileSync(require.resolve("../src/hooks/use-form-draft.ts"), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    }).outputText;
    const exports = {};
    new Function("require", "exports", source)(name => {
      if (name === "react") return react;
      if (name === "@/auth/auth-context") return { useAuth: () => ({ user: { id: owner } }) };
      if (name === "@react-native-async-storage/async-storage") return storage;
      throw new Error(name);
    }, exports);
    return () => {
      index = 0;
      const result = exports.useFormDraft("inquiry:new", { title: "", content: "" });
      effects.splice(0).forEach(run => run());
      return result;
    };
  }
  const settle = () => new Promise(resolve => setImmediate(resolve));
  let render = mount();
  assert.equal(render().ready, false);
  await settle();
  let draft = render();
  draft.update("title", "제목");
  draft.update("content", "작성 중인 내용");
  await settle();
  render = mount();
  render();
  await settle();
  draft = render();
  assert.deepEqual(draft.value, { title: "제목", content: "작성 중인 내용" });
  owner = 1477;
  assert.equal(render().ready, false);
  await settle();
  assert.deepEqual(render().value, { title: "", content: "" });
  owner = 1476;
  render();
  await settle();
  draft = render();
  draft.update("content", "저장 대기 중인 내용");
  await draft.clear();
  assert.equal(rows.has("form-draft:v1:1476:inquiry:new"), false);
  render = mount();
  render();
  await settle();
  assert.deepEqual(render().value, { title: "", content: "" });
});
