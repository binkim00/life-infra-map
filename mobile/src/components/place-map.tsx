import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  Text,
  View,
  StyleSheet,
} from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

import type { Place } from "@/types/place";

const embedUrl =
  process.env.EXPO_PUBLIC_KAKAO_MAP_EMBED_URL ||
  "https://life-infra-map-db.taile29cc8.ts.net/kakao-map-embed.html";
const versionedEmbedUrl = `${embedUrl}${embedUrl.includes("?") ? "&" : "?"}v=compact-map-5`;

const MAX_VISIBLE_MARKERS = 20;

export function PlaceMap({
  place,
  places = [],
  onSelectPlace,
  onCenterChange,
  onMapPress,
  onRequestCurrentLocation,
  displayMode = "overview",
  expanded = false,
  currentLocation = null,
  fitBoundsKey,
}: {
  place?: Place | null;
  places?: Place[];
  onSelectPlace?: (place: Place) => void;
  onCenterChange?: (center: { lat: number; lng: number }) => void;
  onMapPress?: (coordinate: { lat: number; lng: number }) => void;
  onRequestCurrentLocation?: () => void;
  displayMode?: "overview" | "selected";
  expanded?: boolean;
  currentLocation?: { lat: number; lng: number } | null;
  fitBoundsKey?: string | number;
}) {
  const webViewRef = useRef<WebView>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    if (loadState !== "loading") return;
    const timer = setTimeout(() => setLoadState("error"), 15000);
    return () => clearTimeout(timer);
  }, [loadState, reloadKey]);
  const lastPlacesSignatureRef = useRef("");
  const lastSelectedIdRef = useRef<string | null>(null);
  const validPlaces = useMemo(() => {
    const candidates = places.length ? places : place ? [place] : [];
    return candidates.filter(
      (item) =>
        item.lat !== null &&
        item.lat !== undefined &&
        item.lng !== null &&
        item.lng !== undefined &&
        Number.isFinite(Number(item.lat)) &&
        Number.isFinite(Number(item.lng)),
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
    const selectedId = place ? String(place.id) : null;
    const viewportKey = String(
      fitBoundsKey ??
        `${displayMode}:${placesSignature}:${currentLocation?.lat ?? ""}:${currentLocation?.lng ?? ""}`,
    );
    const shouldFocusSelected = Boolean(
      selectedId &&
      lastPlacesSignatureRef.current === placesSignature &&
      lastSelectedIdRef.current !== selectedId,
    );
    lastPlacesSignatureRef.current = placesSignature;
    lastSelectedIdRef.current = selectedId;
    const payload = {
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
      selectedId,
      viewportMode: displayMode,
      viewportKey,
      currentLocation:
        currentLocation &&
        Number.isFinite(currentLocation.lat) &&
        Number.isFinite(currentLocation.lng)
          ? currentLocation
          : null,
      pickerMode: Boolean(onMapPress),
      requestCurrentLocation: Boolean(onRequestCurrentLocation),
    };
    const encodedPayload = encodeURIComponent(JSON.stringify(payload));
    webViewRef.current?.injectJavaScript(`
      (function () {
        window.dispatchEvent(new MessageEvent("message", {
          data: JSON.parse(decodeURIComponent("${encodedPayload}"))
        }));
        const controls = document.getElementById("controls");
        if (controls) controls.style.bottom = "${expanded ? 252 : 18}px";
        if (state.map && !window.__lifeInfraMapCenterListenerAdded) {
          window.__lifeInfraMapCenterListenerAdded = true;
          const reportMapCenter = function () {
            const center = state.map.getCenter();
            window.ReactNativeWebView?.postMessage(JSON.stringify({
              type: "life-infra-map:center-changed",
              lat: center.getLat(),
              lng: center.getLng()
            }));
          };
          kakao.maps.event.addListener(state.map, "idle", reportMapCenter);
          reportMapCenter();
        }
        if (${shouldFocusSelected}) {
          const focusedPlace = state.places.find(
            (item) => String(item.id) === String(state.selectedId)
          );
          if (focusedPlace && state.map) {
            const focusedPosition = new kakao.maps.LatLng(
              focusedPlace.lat,
              focusedPlace.lng
            );
            if (state.map.getLevel() > 4) state.map.setLevel(4);
            state.map.setCenter(focusedPosition);
            state.map.panBy(0, 45);
          }
        }
      })();
      true;
    `);
  }, [
    currentLocation,
    displayMode,
    expanded,
    fitBoundsKey,
    mapPlaces,
    onMapPress,
    onRequestCurrentLocation,
    place,
    validPlaces,
  ]);

  const receiveMessage = useCallback(
    (event: WebViewMessageEvent) => {
      try {
        const data = JSON.parse(event.nativeEvent.data);
        if (data?.type === "life-infra-map:ready") {
          setLoadState("ready");
          sendState();
          return;
        }
        if (data?.type === "life-infra-map:center-changed") {
          const lat = Number(data.lat);
          const lng = Number(data.lng);
          if (Number.isFinite(lat) && Number.isFinite(lng)) {
            onCenterChange?.({ lat, lng });
          }
          return;
        }
        if (data?.type === "life-infra-map:map-pressed") {
          const lat = Number(data.lat);
          const lng = Number(data.lng);
          if (Number.isFinite(lat) && Number.isFinite(lng)) onMapPress?.({ lat, lng });
          return;
        }
        if (data?.type === "life-infra-map:request-current-location") {
          onRequestCurrentLocation?.();
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
    [onCenterChange, onMapPress, onRequestCurrentLocation, onSelectPlace, sendState, validPlaces],
  );

  // WebView가 이미 열린 뒤 검색 결과나 선택 장소가 바뀌는 경우에도
  // 최신 장소 목록을 다시 전달해야 마커와 지도 중심이 갱신됩니다.
  useEffect(() => {
    sendState();
  }, [sendState]);

  return (
    <View style={[styles.map, expanded && styles.expandedMap]}>
      <WebView
        key={reloadKey}
        ref={webViewRef}
        source={{ uri: versionedEmbedUrl }}
        style={{ flex: 1, backgroundColor: "transparent" }}
        javaScriptEnabled
        domStorageEnabled
        cacheEnabled
        nestedScrollEnabled
        overScrollMode="never"
        originWhitelist={["https://*"]}
        onLoadEnd={sendState}
        onMessage={receiveMessage}
        onError={() => setLoadState("error")}
        onHttpError={() => setLoadState("error")}
      />
      {loadState !== "ready" ? (
        <View style={styles.loadOverlay}>
          {loadState === "loading" ? (
            <ActivityIndicator color="#0F766E" />
          ) : null}
          <Text>
            {loadState === "loading"
              ? "지도를 불러오는 중입니다"
              : "지도를 불러오지 못했어요"}
          </Text>
          {loadState === "error" ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                setLoadState("loading");
                setReloadKey((key) => key + 1);
              }}
              style={styles.retry}
            >
              <Text style={{ color: "white" }}>지도 다시 불러오기</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  loadOverlay: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    backgroundColor: "#E9ECEA",
  },
  retry: { padding: 14, borderRadius: 12, backgroundColor: "#0F766E" },
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
