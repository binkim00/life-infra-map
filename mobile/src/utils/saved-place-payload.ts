import type { Place } from "@/types/place";

type SaveablePlace = Place & { source?: string; place_id?: number | null };

export const savedPlacePayload = (place: SaveablePlace) => {
  const candidateSource = place.source || place.result_source || "";
  const isDb = candidateSource === "db" || candidateSource === "local_db" ||
    (!candidateSource && /^db:\d+$/.test(String(place.id)));
  const rawDbId = place.place_id ?? (isDb ? String(place.id).replace(/^db:/, "") : null);
  const placeId = isDb && rawDbId != null && /^\d+$/.test(String(rawDbId))
    ? Number(rawDbId) : null;
  const source = placeId ? "local_db" : candidateSource === "kakao" || candidateSource === "web"
    ? candidateSource : "other";

  return {
    placeId,
    externalId: place.external_id || place.kakao_place_id || "",
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
