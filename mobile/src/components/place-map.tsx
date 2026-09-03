import { useCallback, useMemo, useRef } from "react";
import { StyleSheet } from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

import type { Place } from "@/types/place";

const embedUrl =
  process.env.EXPO_PUBLIC_KAKAO_MAP_EMBED_URL ||
  "https://life-infra-map-db.taile29cc8.ts.net/kakao-map-embed.html";

export function PlaceMap({
  place,
  places = [],
  onSelectPlace,
}: {
  place?: Place | null;
  places?: Place[];
  onSelectPlace?: (place: Place) => void;
}) {
  const webViewRef = useRef<WebView>(null);
  const validPlaces = useMemo(() => {
    const candidates = places.length ? places : place ? [place] : [];
    return candidates.filter(
      (item) =>
        Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lng)),
    );
  }, [place, places]);

  const sendState = useCallback(() => {
    const payload = {
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
    };
    const encodedPayload = encodeURIComponent(JSON.stringify(payload));
    webViewRef.current?.injectJavaScript(`
      window.dispatchEvent(new MessageEvent("message", {
        data: JSON.parse(decodeURIComponent("${encodedPayload}"))
      }));
      true;
    `);
  }, [place, validPlaces]);

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

  return (
    <WebView
      ref={webViewRef}
      source={{ uri: embedUrl }}
      style={styles.map}
      javaScriptEnabled
      domStorageEnabled
      originWhitelist={["https://*"]}
      onLoadEnd={sendState}
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
