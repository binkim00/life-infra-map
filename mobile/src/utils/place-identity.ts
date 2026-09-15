import type { Place } from "@/types/place";

/** Keep markers from different providers distinct even when their numeric IDs match. */
export const placeIdentity = (place: Place) => {
  const source = place.result_source || place.source_name || "";
  const id = place.external_id || place.id;
  return source ? `${source}:${id}` : String(id);
};
