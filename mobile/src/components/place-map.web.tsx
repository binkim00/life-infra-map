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
};

const embedUrl =
  process.env.EXPO_PUBLIC_KAKAO_MAP_EMBED_URL ||
  "http://localhost:5173/kakao-map-embed.html";

export function PlaceMap({ place, places = [], onSelectPlace }: PlaceMapProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const validPlaces = useMemo(() => {
    const candidates = places.length ? places : place ? [place] : [];
    return candidates.filter(
      (item) =>
        Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lng)),
    );
  }, [place, places]);

  const sendState = useCallback(() => {
    frameRef.current?.contentWindow?.postMessage(
      {
        type: "life-infra-map:set-places",
        places: validPlaces.map((item, index) => ({
          id: String(item.id),
          name: item.name,
          category: item.category_label || item.category || "",
          lat: Number(item.lat),
          lng: Number(item.lng),
          label: String(index + 1),
        })),
        selectedId: place ? String(place.id) : null,
      },
      new URL(embedUrl).origin,
    );
  }, [place, validPlaces]);

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
      src={embedUrl}
      title="카카오 장소 지도"
      onLoad={sendState}
      style={styles.frame}
    />
  );
}

const styles: Record<string, CSSProperties> = {
  frame: {
    width: "100%",
    height: 320,
    display: "block",
    border: 0,
    borderRadius: 20,
    background: "#E9ECEA",
  },
};
