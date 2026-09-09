// 순수 상태/지도 브리지 회귀 검사. 실기기 E2E의 대체가 아니다.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../mobile/package.json', import.meta.url));
const ts = require('typescript');
const draftSource = fs.readFileSync(new URL('../mobile/src/utils/place-report-draft.ts', import.meta.url), 'utf8');
const exports = {};
vm.runInNewContext(ts.transpileModule(draftSource, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
  exports, require: () => ({}),
});
const key = exports.reportDraftKey;
assert.equal(key(), 'place-report-draft:v2:new-place');
assert.equal(key('42'), 'place-report-draft:v2:42');
assert.notEqual(key(undefined, '상호A|부산'), key(undefined, '상호B|부산'));
assert.notEqual(key(undefined, '상호A|부산'), key(undefined, '상호A|서울'));

const html = fs.readFileSync(new URL('../frontend/kakao-map-embed.html', import.meta.url), 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const buttons = new Map(); const handlers = new Map(); const messages = [];
const elements = new Map();
const document = { getElementById(id) {
  if (!elements.has(id)) elements.set(id, { style: {}, classList: { add() {} }, textContent: '', addEventListener: (type, fn) => buttons.set(`${id}:${type}`, fn) });
  return elements.get(id);
} };
let map;
class LatLng { constructor(lat, lng) { this.lat = lat; this.lng = lng; } getLat() { return this.lat; } getLng() { return this.lng; } }
class MapStub { constructor(_, opts) { this.center = opts.center; this.level = opts.level; map = this; } setCenter(x) { this.center = x; } panTo(x) { this.center = x; } getCenter() { return this.center; } setLevel(x) { this.level = x; } getLevel() { return this.level; } setBounds() { this.center = 'bounds'; } }
const maps = { Map: MapStub, LatLng, LatLngBounds: class { extend() {} }, Marker: class { setMap() {} }, MarkerImage: class {}, Size: class {}, Point: class {}, event: { addListener() {} }, load(fn) { fn(); } };
const window = { kakao: { maps }, parent: { postMessage(x) { messages.push(x); } }, addEventListener(type, fn) { handlers.set(type, fn); } };
vm.runInNewContext(script, { window, document, kakao: window.kakao, encodeURIComponent });
const update = (extra = {}) => handlers.get('message')({ data: {
  type: 'life-infra-map:set-places', viewportKey: 'results-1', viewportMode: 'selected', selectedId: 'busan',
  places: [{ id: 'busan', name: '부산 장소', lat: 35.1, lng: 129.1 }, { id: 'seoul', name: '서울 장소', lat: 37.5, lng: 127 }],
  currentLocation: { lat: 35.09, lng: 128.85 }, requestCurrentLocation: true, ...extra,
} });
update();
assert.equal(map.center.lat, 35.1, '검색 결과 위치 우선');
buttons.get('recenter:click')();
assert.equal(messages.at(-1).type, 'life-infra-map:request-current-location', '실제 GPS 요청');
update({ viewportKey: 'results-2', currentLocation: { lat: 35.08, lng: 128.84 } });
assert.equal(map.center.lat, 35.08, '결과 bounds가 새 현재 위치 이동을 덮어쓰지 않음');
update({ viewportKey: 'results-2', selectedId: 'seoul' });
assert.equal(map.center.lat, 35.08, '같은 viewport의 상태 갱신은 지도 이동 안 함');
console.log('PASS: draft identity and map result/current-location/viewport regression assertions');
