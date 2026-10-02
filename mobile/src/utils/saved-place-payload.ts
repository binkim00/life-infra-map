import type { Place } from "@/types/place";

type SaveablePlace = Place & { source?: string; place_id?: number | null };

export const savedPlacePayload = (place: SaveablePlace) => {
  // `source` describes data provenance (for example kakao_local) while
  // `result_source` identifies whether the search hit came from our DB.
  const candidateSource = place.result_source || place.source || "";
  const isDb = candidateSource === "db" || candidateSource === "local_db" ||
    (!candidateSource && /^db:\d+$/.test(String(place.id)));
  const rawDbId = place.place_id ?? (isDb ? String(place.id).replace(/^db:/, "") : null);
  const placeId = isDb && rawDbId != null && /^\d+$/.test(String(rawDbId))
    ? Number(rawDbId) : null;
  const source = placeId ? "local_db" : candidateSource === "kakao" || candidateSource === "web"
    ? candidateSource : "other";
  const externalId = place.external_id || place.kakao_place_id || "";
  const placeKey = placeId
    ? `place:${placeId}`
    : externalId
      ? `${source}:${externalId}`
      : `snapshot:${source}:${place.name.slice(0, 100)}:${place.lat ?? ""}:${place.lng ?? ""}`;

  return {
    placeKey,
    placeId,
    externalId,
    source,
    name: place.name,
    category: place.category,
    address: place.address || "",
    lat: Number.isFinite(Number(place.lat)) ? place.lat : null,
    lng: Number.isFinite(Number(place.lng)) ? place.lng : null,
    detailUrl: place.place_url || "",
    kakaoPlaceUrl: place.kakao_place_url || "",
    raw: {},
  };
};
