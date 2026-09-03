import { useCallback, useEffect, useMemo, useRef } from "react";
import { StyleSheet } from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

import type { Place } from "@/types/place";

const embedUrl =
  process.env.EXPO_PUBLIC_KAKAO_MAP_EMBED_URL ||
  "https://life-infra-map-db.taile29cc8.ts.net/kakao-map-embed.html";
const versionedEmbedUrl = `${embedUrl}${embedUrl.includes("?") ? "&" : "?"}v=compact-map-2`;

const MAX_VISIBLE_MARKERS = 20;

export function PlaceMap({
  place,
  places = [],
  onSelectPlace,
  displayMode = "overview",
  expanded = false,
  currentLocation = null,
}: {
  place?: Place | null;
  places?: Place[];
  onSelectPlace?: (place: Place) => void;
  displayMode?: "overview" | "selected";
  expanded?: boolean;
  currentLocation?: { lat: number; lng: number } | null;
}) {
  const webViewRef = useRef<WebView>(null);
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
    const payload = {
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
    };
    const encodedPayload = encodeURIComponent(JSON.stringify(payload));
    webViewRef.current?.injectJavaScript(`
      window.dispatchEvent(new MessageEvent("message", {
        data: JSON.parse(decodeURIComponent("${encodedPayload}"))
      }));
      true;
    `);
  }, [currentLocation, displayMode, mapPlaces, place, validPlaces]);

  const receiveMessage = useCallback(
    (event: WebViewMessageEvent) => {
      try {
        const data = JSON.parse(event.nativeEvent.data);
        if (data?.type === "life-infra-map:ready") {
          sendState();
          return;
        }
        if (data?.type !== "life-infra-map:select-place") return;
        const selected = validPlaces.find(
          (item) => String(item.id) === String(data.id),
        );
        if (selected) onSelectPlace?.(selected);
      } catch {
        // 지도 페이지가 보내지 않은 메시지는 무시합니다.
      }
    },
    [onSelectPlace, sendState, validPlaces],
  );

  // WebView가 이미 열린 뒤 검색 결과나 선택 장소가 바뀌는 경우에도
  // 최신 장소 목록을 다시 전달해야 마커와 지도 중심이 갱신됩니다.
  useEffect(() => {
    sendState();
  }, [sendState]);

  return (
    <WebView
      ref={webViewRef}
      source={{ uri: versionedEmbedUrl }}
      style={[styles.map, expanded && styles.expandedMap]}
      javaScriptEnabled
      domStorageEnabled
      cacheEnabled={false}
      nestedScrollEnabled
      overScrollMode="never"
      originWhitelist={["https://*"]}
      onLoadEnd={sendState}
      onMessage={receiveMessage}
    />
  );
}

const styles = StyleSheet.create({
  map: {
    width: "100%",
    height: 390,
    borderRadius: 20,
    backgroundColor: "#E9ECEA",
  },
  expandedMap: {
    flex: 1,
    height: "100%",
    borderRadius: 0,
  },
});
