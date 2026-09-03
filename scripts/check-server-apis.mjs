const publicBase = (
  process.env.LIFE_INFRA_PUBLIC_BASE ||
  "https://life-infra-map-db.taile29cc8.ts.net"
).replace(/\/$/, "");

const withinRadius = (place, radius) =>
  Number(place.distance) >= 0 && Number(place.distance) <= radius;

const canonicalCategoryMatches = (place, category) => {
  if (place.result_source === "db") return place.category === category;
  const segments = String(place.category || "")
    .split(">")
    .map((segment) => segment.trim());
  if (category === "city_park") return segments.includes("공원");
  if (category === "cafe") {
    const text = `${place.name || ""} ${place.category || ""}`.toLowerCase();
    return (
      segments.includes("카페") &&
      !/(pc방|게임방|보드카페|룸카페|키즈카페)/.test(text)
    );
  }
  if (category === "restaurant") {
    return (
      segments.includes("음식점") &&
      !segments.some((segment) => /(카페|간식|술집|제과|베이커리)/.test(segment))
    );
  }
  return false;
};

const onlyCategory = (data, category, radius, minimumResults = 1) =>
  Array.isArray(data?.results) &&
  data.results.length >= minimumResults &&
  data.results.every(
    (place) =>
      canonicalCategoryMatches(place, category) && withinRadius(place, radius),
  );

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
    url: `${publicBase}/django/api/recommendations/place-search/?q=${encodeURIComponent("공원")}&source=all&lat=35.1544&lng=129.0606&radius=3000&limit=30`,
    validate: (data) =>
      onlyCategory(data, "city_park", 3000, 5) &&
      data.results.every(
        (place) =>
          !/(주차장|화장실|매점|관리사무소|출입구)$/.test(place.name || ""),
      ),
  },
  {
    name: "주변 카페 검색",
    url: `${publicBase}/django/api/recommendations/place-search/?q=${encodeURIComponent("카페")}&source=all&lat=35.1544&lng=129.0606&radius=3000&limit=30`,
    validate: (data) => onlyCategory(data, "cafe", 3000, 5),
  },
  {
    name: "주변 식당 검색",
    url: `${publicBase}/django/api/recommendations/place-search/?q=${encodeURIComponent("식당")}&source=all&lat=35.1544&lng=129.0606&radius=3000&limit=30`,
    validate: (data) => onlyCategory(data, "restaurant", 3000, 5),
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
    const startedAt = performance.now();
    const response = await fetch(check.url, {
      method: check.method || "GET",
      headers: check.body ? { "Content-Type": "application/json" } : undefined,
      body: check.body ? JSON.stringify(check.body) : undefined,
      signal: AbortSignal.timeout(30_000),
    });
    const data = await response.json().catch(() => null);
    const elapsedMs = Math.round(performance.now() - startedAt);
    const fastEnough = elapsedMs <= 3000;
    const valid = response.ok && fastEnough && check.validate(data);
    const resultCount = Array.isArray(data?.results)
      ? `, 결과 ${data.results.length}건`
      : "";
    console.log(
      `${valid ? "PASS" : "FAIL"} ${check.name}: HTTP ${response.status}, ${elapsedMs}ms${resultCount}`,
    );
    if (!valid) failed = true;
  } catch (error) {
    failed = true;
    console.error(`FAIL ${check.name}: ${error.message}`);
  }
}

if (failed) process.exitCode = 1;
