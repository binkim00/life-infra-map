/** Presentation only: never infer a search action or a condition from user text. */
type RecordValue = Record<string, any>;
const CATEGORY_LABELS: Record<string, string> = {
  cafe: "카페", restaurant: "음식점", city_park: "공원/산책", park: "공원/산책",
  walking_trail: "공원/산책", parking: "주차장", tourist_attraction: "관광지",
  tourism: "관광지", pharmacy: "약국", hospital: "의료", toilet: "화장실",
  shopping: "쇼핑", shopping_mall: "쇼핑", convenience_store: "생활 편의",
  smoking_area: "흡연구역", library: "도서관", shelter: "쉼터",
};
const label = (value: unknown): string => {
  if (typeof value === "object" && value) return label((value as RecordValue).label || (value as RecordValue).name);
  if (typeof value !== "string") return "";
  return CATEGORY_LABELS[value] || (/[가-힣]/.test(value) && !value.includes("_") ? value.trim() : "");
};
export const categoryDisplay = (value: unknown): string => label(value) || "기타";
const list = (value: unknown): unknown[] => Array.isArray(value) ? value : value ? [value] : [];

export const placeKey = (place: RecordValue | null | undefined): string => {
  if (!place) return "";
  if (place.place_key) return String(place.place_key);
  if (place.placeKey) return String(place.placeKey);
  const source = place.result_source || place.resultSource || place.source || place.source_name || place.sourceName || "db";
  const id = place.external_id || place.externalId || place.place_id || place.savedPlaceId || place.id;
  return `${source}:${typeof id === "string" && id.startsWith(`${source}:`) ? id.slice(source.length + 1) : id ?? `${place.name || ""}:${place.address || ""}`}`;
};

export const conditionChips = (plan: RecordValue | null | undefined): string[] => {
  if (!plan) return [];
  const frame = plan.place_intent_frame || plan.placeIntentFrame || plan.frame || {};
  const chips = [label(frame.anchor_location || frame.anchorLocation || plan.locationQuery || plan.location_query)];
  const categories = list(frame.candidate_place_types || frame.candidatePlaceTypes || frame.candidate_category_codes || frame.category || plan.categoryKeyword);
  chips.push(...categories.map(label));
  const required = list(frame.required_features || frame.requiredFeatures || frame.required_conditions || frame.requiredConditions);
  chips.push(...required.map((value) => label(value)).filter(Boolean).map((value) => `${value} · 필수`));
  const preferred = list(frame.preferred_features || frame.preferredFeatures);
  chips.push(...preferred.map(label).filter(Boolean).map((value) => `${value} · 선호`));
  const radius = Number(frame.radius_m || frame.radiusM || frame.radius || plan.radius_m || plan.radius || plan.searchRadius);
  if (radius > 0) chips.push(radius >= 1000 ? `${radius / 1000}km 이내` : `${radius}m 이내`);
  return [...new Set(chips.filter(Boolean))];
};

export const keepsPreviousResults = (action: string): boolean => Boolean(action && !["search", "reset_conversation", "undo_last_change"].includes(action));

export const referencedPlaceKeys = (response: RecordValue, previous: RecordValue[]): string[] => {
  const explicit = list(response.referenced_place_keys || response.place_keys).filter((key): key is string => typeof key === "string");
  if (explicit.length) return explicit;
  const references = list(response.referenced_results || response.results) as RecordValue[];
  const keys = references.map(placeKey).filter((key) => previous.some((place) => placeKey(place) === key));
  if (keys.length) return [...new Set(keys)];
  return [...new Set(list(response.result_indexes).filter((index): index is number => Number.isInteger(index) && Number(index) >= 0)
    .map((index) => placeKey(previous[index])).filter(Boolean))];
};

export const nextBackAction = (state: {
  keyboard?: boolean; detailHistory?: boolean; detail?: boolean;
  panel?: "collapsed" | "peek" | "expanded"; canGoBack?: boolean; root?: boolean;
}) => state.keyboard ? "keyboard" : state.detailHistory ? "detailHistory" : state.detail ? "detail"
  : state.panel === "expanded" ? "peek" : state.panel === "peek" ? "collapsed"
    : state.canGoBack ? "history" : state.root ? "exit" : "home";
