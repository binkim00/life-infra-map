import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type CSSProperties,
} from "react";

import type { Place } from "@/types/place";

type PlaceMapProps = {
  place?: Place | null;
  places?: Place[];
  onSelectPlace?: (place: Place) => void;
  onCenterChange?: (center: { lat: number; lng: number }) => void;
  onMapPress?: (coordinate: { lat: number; lng: number }) => void;
  onRequestCurrentLocation?: () => void;
  displayMode?: "overview" | "selected";
  focusSelected?: boolean;
  expanded?: boolean;
  currentLocation?: { lat: number; lng: number } | null;
  fitBoundsKey?: string | number;
};

const embedUrl =
  process.env.EXPO_PUBLIC_KAKAO_MAP_EMBED_URL ||
  "http://localhost:5173/kakao-map-embed.html";
const versionedEmbedUrl = `${embedUrl}${embedUrl.includes("?") ? "&" : "?"}v=search-viewport-8`;

const MAX_VISIBLE_MARKERS = 20;

export function PlaceMap({
  place,
  places = [],
  onSelectPlace,
  onCenterChange,
  onMapPress,
  onRequestCurrentLocation,
  displayMode = "overview",
  focusSelected = false,
  expanded = false,
  currentLocation = null,
  fitBoundsKey,
}: PlaceMapProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const validPlaces = useMemo(() => {
    const candidates = places.length ? places : place ? [place] : [];
    return candidates.filter(
      (item) =>
        item.lat !== null &&
        item.lat !== undefined &&
        item.lng !== null &&
        item.lng !== undefined &&
        Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lng)),
    );
  }, [place, places]);
  const mapPlaces = useMemo(() => {
    if (displayMode === "selected") return place ? [place] : [];
    const visible = validPlaces.slice(0, MAX_VISIBLE_MARKERS);
    if (!place || visible.some((item) => String(item.id) === String(place.id)))
      return visible;
    return [...visible.slice(0, MAX_VISIBLE_MARKERS - 1), place];
  }, [displayMode, place, validPlaces]);

  const sendState = useCallback(() => {
    const placesSignature = mapPlaces
      .map((item) => `${item.id}:${item.lat}:${item.lng}`)
      .join("|");
    frameRef.current?.contentWindow?.postMessage(
      {
        type: "life-infra-map:set-places",
        places: mapPlaces.map((item) => ({
          id: String(item.id),
          name: item.name,
          category: item.category_label || item.category || "",
          lat: Number(item.lat),
          lng: Number(item.lng),
          label: String(
            validPlaces.findIndex(
              (candidate) => String(candidate.id) === String(item.id),
            ) + 1,
          ),
        })),
        selectedId: place ? String(place.id) : null,
        viewportMode: focusSelected ? "selected" : displayMode,
        viewportKey: String(
          fitBoundsKey ??
            `${displayMode}:${placesSignature}:${currentLocation?.lat ?? ""}:${currentLocation?.lng ?? ""}`,
        ),
        currentLocation:
          currentLocation &&
          Number.isFinite(currentLocation.lat) &&
          Number.isFinite(currentLocation.lng)
            ? currentLocation
            : null,
        pickerMode: Boolean(onMapPress),
        requestCurrentLocation: Boolean(onRequestCurrentLocation),
      },
      new URL(embedUrl).origin,
    );
  }, [currentLocation, displayMode, focusSelected, fitBoundsKey, mapPlaces, onMapPress, onRequestCurrentLocation, place, validPlaces]);

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.source !== frameRef.current?.contentWindow) return;
      if (event.data?.type === "life-infra-map:ready") sendState();
      if (event.data?.type === "life-infra-map:center-changed") {
        const lat = Number(event.data.lat);
        const lng = Number(event.data.lng);
        if (Number.isFinite(lat) && Number.isFinite(lng)) {
          onCenterChange?.({ lat, lng });
        }
        return;
      }
      if (event.data?.type === "life-infra-map:map-pressed") {
        const lat = Number(event.data.lat);
        const lng = Number(event.data.lng);
        if (Number.isFinite(lat) && Number.isFinite(lng)) onMapPress?.({ lat, lng });
        return;
      }
      if (event.data?.type === "life-infra-map:request-current-location") {
        onRequestCurrentLocation?.();
        return;
      }
      if (event.data?.type !== "life-infra-map:select-place") return;
      const selected = validPlaces.find(
        (item) => String(item.id) === String(event.data.id),
      );
      if (selected) onSelectPlace?.(selected);
    };
    window.addEventListener("message", receive);
    sendState();
    return () => window.removeEventListener("message", receive);
  }, [onCenterChange, onMapPress, onRequestCurrentLocation, onSelectPlace, sendState, validPlaces]);

  return (
    <iframe
      ref={frameRef}
      src={versionedEmbedUrl}
      title="카카오 장소 지도"
      onLoad={sendState}
      style={{ ...styles.frame, ...(expanded ? styles.expandedFrame : {}) }}
    />
  );
}

const styles: Record<string, CSSProperties> = {
  frame: {
    width: "100%",
    height: 390,
    display: "block",
    border: 0,
    borderRadius: 20,
    background: "#E9ECEA",
  },
  expandedFrame: {
    height: "100%",
    borderRadius: 0,
  },
};
