import { placeKey } from "../../../shared/search-ux";
import type { Place } from "@/types/place";

/** Provider identity shared by lists and embedded maps. */
export const placeIdentity = (place: Place) => placeKey(place);
