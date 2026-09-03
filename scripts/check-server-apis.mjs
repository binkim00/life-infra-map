const publicBase = (
  process.env.LIFE_INFRA_PUBLIC_BASE ||
  "https://life-infra-map-db.taile29cc8.ts.net"
).replace(/\/$/, "");

const checks = [
  {
    name: "Django health",
    url: `${publicBase}/django/api/recommendations/health/`,
    validate: (data) => Boolean(data?.status || data?.message),
  },
  {
    name: "Spring health",
    url: `${publicBase}/spring/api/health`,
    validate: (data) => Boolean(data?.message),
  },
  {
    name: "일반 장소 검색",
    url: `${publicBase}/django/api/recommendations/place-search/?q=${encodeURIComponent("부산역 약국")}&source=all&limit=5`,
    validate: (data) => Array.isArray(data?.results) && data.results.length > 0,
  },
  {
    name: "현재 위치 공원 검색",
    url: `${publicBase}/django/api/recommendations/place-search/?q=${encodeURIComponent("공원")}&source=all&lat=35.1544&lng=129.0606&limit=6`,
    validate: (data) =>
      Array.isArray(data?.results) &&
      data.results.length > 0 &&
      data.results.every((place) => Number(place.distance) >= 0),
  },
  {
    name: "상황 기반 검색",
    url: `${publicBase}/django/api/recommendations/ai-search/`,
    method: "POST",
    body: {
      query: "부산 서면에서 조용히 노트북 작업할 수 있는 카페",
      limit: 5,
    },
    validate: (data) => Array.isArray(data?.results) && data.results.length > 0,
  },
  {
    name: "게시판 목록",
    url: `${publicBase}/spring/api/boards/posts?board_type=free`,
    validate: (data) => Array.isArray(data),
  },
];

let failed = false;

for (const check of checks) {
  try {
    const response = await fetch(check.url, {
      method: check.method || "GET",
      headers: check.body ? { "Content-Type": "application/json" } : undefined,
      body: check.body ? JSON.stringify(check.body) : undefined,
      signal: AbortSignal.timeout(30_000),
    });
    const data = await response.json().catch(() => null);
    const valid = response.ok && check.validate(data);
    console.log(`${valid ? "PASS" : "FAIL"} ${check.name}: HTTP ${response.status}`);
    if (!valid) failed = true;
  } catch (error) {
    failed = true;
    console.error(`FAIL ${check.name}: ${error.message}`);
  }
}

if (failed) process.exitCode = 1;
