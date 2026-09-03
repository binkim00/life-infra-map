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
  displayMode?: "overview" | "selected";
  expanded?: boolean;
  currentLocation?: { lat: number; lng: number } | null;
};

const embedUrl =
  process.env.EXPO_PUBLIC_KAKAO_MAP_EMBED_URL ||
  "http://localhost:5173/kakao-map-embed.html";
const versionedEmbedUrl = `${embedUrl}${embedUrl.includes("?") ? "&" : "?"}v=compact-map-2`;

const MAX_VISIBLE_MARKERS = 8;

export function PlaceMap({
  place,
  places = [],
  onSelectPlace,
  displayMode = "overview",
  expanded = false,
  currentLocation = null,
}: PlaceMapProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const validPlaces = useMemo(() => {
    const candidates = places.length ? places : place ? [place] : [];
    return candidates.filter(
      (item) =>
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
    frameRef.current?.contentWindow?.postMessage(
      {
        type: "life-infra-map:set-places",
        places: mapPlaces.map((item) => ({
          id: String(item.id),
          name: item.name,
          category: item.category_label || item.category || "",
          lat: Number(item.lat),
          lng: Number(item.lng),
          label: String(validPlaces.findIndex((candidate) => String(candidate.id) === String(item.id)) + 1),
        })),
        selectedId: place ? String(place.id) : null,
        viewportMode: displayMode,
        currentLocation:
          currentLocation &&
          Number.isFinite(currentLocation.lat) &&
          Number.isFinite(currentLocation.lng)
            ? currentLocation
            : null,
      },
      new URL(embedUrl).origin,
    );
  }, [currentLocation, displayMode, mapPlaces, place, validPlaces]);

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.source !== frameRef.current?.contentWindow) return;
      if (event.data?.type === "life-infra-map:ready") sendState();
      if (event.data?.type !== "life-infra-map:select-place") return;
      const selected = validPlaces.find(
        (item) => String(item.id) === String(event.data.id),
      );
      if (selected) onSelectPlace?.(selected);
    };
    window.addEventListener("message", receive);
    sendState();
    return () => window.removeEventListener("message", receive);
  }, [onSelectPlace, sendState, validPlaces]);

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
