import { useCallback, useMemo } from "react";
import { StyleSheet } from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

import type { Place } from "@/types/place";
import { buildPlaceMapHtml } from "./place-map-html";

export function PlaceMap({
  place,
  places = [],
  onSelectPlace,
}: {
  place?: Place | null;
  places?: Place[];
  onSelectPlace?: (place: Place) => void;
}) {
  const validPlaces = useMemo(() => {
    const candidates = places.length ? places : place ? [place] : [];
    return candidates.filter(
      (item) =>
        Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lng)),
    );
  }, [place, places]);

  const mapHtml = useMemo(
    () =>
      buildPlaceMapHtml(
        validPlaces.map((item, index) => ({
        id: String(item.id),
        name: item.name,
        lat: Number(item.lat),
        lng: Number(item.lng),
        label: String(index + 1),
        })),
        place ? String(place.id) : null,
      ),
    [place, validPlaces],
  );

  const receiveMessage = useCallback(
    (event: WebViewMessageEvent) => {
      try {
        const data = JSON.parse(event.nativeEvent.data);
        if (data?.type !== "life-infra-map:select-place") return;
        const selected = validPlaces.find(
          (item) => String(item.id) === String(data.id),
        );
        if (selected) onSelectPlace?.(selected);
      } catch {
        // 지도 페이지가 보내지 않은 메시지는 무시합니다.
      }
    },
    [onSelectPlace, validPlaces],
  );

  return (
    <WebView
      source={{ html: mapHtml, baseUrl: "https://life-infra-map.app/" }}
      style={styles.map}
      javaScriptEnabled
      domStorageEnabled
      originWhitelist={["*"]}
      onMessage={receiveMessage}
    />
  );
}

const styles = StyleSheet.create({
  map: {
    width: "100%",
    height: 320,
    borderRadius: 20,
    backgroundColor: "#E9ECEA",
  },
});
