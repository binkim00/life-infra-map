import { router, useLocalSearchParams } from "expo-router";
import * as Location from "expo-location";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { recommendationApi, searchMapPlaces } from "@/api/recommendations";
import { useAuth } from "@/auth/auth-context";
import { BottomNav } from "@/components/bottom-nav";
import { PlaceMap } from "@/components/place-map";
import {
  BottomTabInset,
  Palette,
  Radius,
  Shadow,
  Spacing,
} from "@/constants/theme";
import type { Place } from "@/types/place";

const FILTERS = [
  { label: "전체", query: "" },
  { label: "주차장", query: "주차장" },
  { label: "화장실", query: "공중화장실" },
  { label: "공원", query: "공원" },
  { label: "쉼터", query: "쉼터" },
] as const;

const formatDistance = (distance?: number) =>
  distance === undefined
    ? "거리 정보 없음"
    : distance < 1000
      ? `${Math.round(distance)}m`
      : `${(distance / 1000).toFixed(1)}km`;

const mapUrl = (place: Place) =>
  place.place_url ||
  place.kakao_place_url ||
  `https://map.kakao.com/link/map/${encodeURIComponent(place.name)},${place.lat},${place.lng}`;

export default function ExploreScreen() {
  const { requireLogin, isLoggedIn } = useAuth();
  const params = useLocalSearchParams<{ q?: string; placeId?: string }>();
  const initialQuery = typeof params.q === "string" ? params.q : "";
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);
  const [places, setPlaces] = useState<Place[]>([]);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [status, setStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >(initialQuery ? "loading" : "idle");
  const [message, setMessage] = useState("");
  const [center, setCenter] = useState({
    lat: 37.5665,
    lng: 126.978,
    label: "서울시청 기준",
  });

  const runSearch = useCallback(
    (nextQuery = query) => {
      const trimmed = nextQuery.trim();
      if (!trimmed) {
        setMessage("검색어를 입력하거나 시설 종류를 선택하세요.");
        return;
      }
      setQuery(trimmed);
      setStatus("loading");
      setMessage("");
      setSubmittedQuery(trimmed);
    },
    [query],
  );

  useEffect(() => {
    if (!submittedQuery) return;
    const controller = new AbortController();
    searchMapPlaces({
      query: submittedQuery,
      lat: center.lat,
      lng: center.lng,
      signal: controller.signal,
    })
      .then((data) => {
        setPlaces(data.results);
        const requested = data.results.find(
          (place) => String(place.id) === params.placeId,
        );
        setSelectedPlace(requested || data.results[0] || null);
        setStatus("success");
        if (isLoggedIn)
          void recommendationApi.saveSearchLog({
            query: submittedQuery,
            search_mode: "keyword_search",
            lat: center.lat,
            lng: center.lng,
            target_query: submittedQuery,
            result_count: data.results.length,
            db_result_count: data.candidate_counts?.db || 0,
            kakao_result_count: data.candidate_counts?.kakao || 0,
            ai_web_result_count: 0,
            search_plan_snapshot: {},
          });
        if (!data.results.length)
          setMessage(
            "조건에 맞는 장소가 없습니다. 다른 검색어를 입력해 보세요.",
          );
      })
      .catch((error) => {
        if (error?.name === "AbortError") return;
        setPlaces([]);
        setSelectedPlace(null);
        setStatus("error");
        setMessage(
          error instanceof Error ? error.message : "서버에 연결할 수 없습니다.",
        );
      });
    return () => controller.abort();
  }, [submittedQuery, params.placeId, center.lat, center.lng, isLoggedIn]);

  const useCurrentLocation = async () => {
    const permission = await Location.requestForegroundPermissionsAsync();
    if (!permission.granted)
      return setMessage("현재 위치를 사용하려면 위치 권한이 필요합니다.");
    const position = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });
    setCenter({
      lat: position.coords.latitude,
      lng: position.coords.longitude,
      label: "현재 위치 기준",
    });
  };

  const saveSelectedPlace = async () => {
    if (!selectedPlace || !requireLogin()) return;
    try {
      await recommendationApi.savePlace({
        placeKey: `${selectedPlace.result_source || "db"}:${selectedPlace.external_id || selectedPlace.id}`,
        placeId: selectedPlace.result_source === "db" ? selectedPlace.id : null,
        externalId: selectedPlace.external_id || "",
        source: selectedPlace.result_source || "db",
        name: selectedPlace.name,
        category: selectedPlace.category,
        address: selectedPlace.address,
        lat: selectedPlace.lat,
        lng: selectedPlace.lng,
        detailUrl: selectedPlace.place_url || "",
        kakaoPlaceUrl: selectedPlace.kakao_place_url || "",
        raw: {},
      });
      setMessage("장소를 저장했습니다.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "장소를 저장하지 못했습니다.",
      );
    }
  };

  const activeFilter = useMemo(
    () =>
      FILTERS.find((filter) => filter.query === submittedQuery)?.label ??
      "전체",
    [submittedQuery],
  );

  return (
    <View style={styles.screen}>
      <SafeAreaView style={styles.safeArea} edges={["top", "left", "right"]}>
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.header}>
            <View>
              <Text style={styles.kicker}>EXPLORE</Text>
              <Text style={styles.title}>생활 시설 찾기</Text>
            </View>
            <Pressable onPress={useCurrentLocation}>
              <Text style={styles.baseLocation}>{center.label}</Text>
            </Pressable>
          </View>

          <View style={styles.searchBox}>
            <TextInput
              value={query}
              onChangeText={setQuery}
              onSubmitEditing={() => runSearch()}
              placeholder="예: 종로 무료 주차장"
              placeholderTextColor="#8A918E"
              returnKeyType="search"
              style={styles.searchInput}
            />
            <Pressable
              onPress={() => runSearch()}
              style={({ pressed }) => [
                styles.searchButton,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.searchButtonLabel}>검색</Text>
            </Pressable>
          </View>

          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.filters}
          >
            {FILTERS.map((filter) => {
              const active = activeFilter === filter.label;
              return (
                <Pressable
                  key={filter.label}
                  onPress={() =>
                    filter.query ? runSearch(filter.query) : setQuery("")
                  }
                  style={[styles.filter, active && styles.filterActive]}
                >
                  <Text
                    style={[
                      styles.filterLabel,
                      active && styles.filterLabelActive,
                    ]}
                  >
                    {filter.label}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>

          <View style={styles.mapSection}>
            <PlaceMap
              place={selectedPlace}
              places={places}
              onSelectPlace={setSelectedPlace}
            />
            {selectedPlace ? (
              <View style={styles.selectedSummary}>
                <View style={styles.selectedCopy}>
                  <Text numberOfLines={1} style={styles.selectedName}>
                    {selectedPlace.name}
                  </Text>
                  <Text numberOfLines={1} style={styles.selectedAddress}>
                    {selectedPlace.address || selectedPlace.category_label}
                  </Text>
                </View>
                <Pressable
                  onPress={() => Linking.openURL(mapUrl(selectedPlace))}
                  style={styles.routeButton}
                >
                  <Text style={styles.routeButtonLabel}>지도 열기</Text>
                </Pressable>
              </View>
            ) : null}
          </View>

          {selectedPlace ? (
            <View style={styles.placeActions}>
              <Pressable
                onPress={saveSelectedPlace}
                style={[uiButton.secondary]}
              >
                <Text style={uiButton.secondaryText}>저장</Text>
              </Pressable>
              <Pressable
                onPress={() =>
                  requireLogin() &&
                  router.push({
                    pathname: "/place-report",
                    params: {
                      placeId: String(selectedPlace.id),
                      name: selectedPlace.name,
                      address: selectedPlace.address || "",
                      lat: String(selectedPlace.lat),
                      lng: String(selectedPlace.lng),
                    },
                  })
                }
                style={[uiButton.secondary]}
              >
                <Text style={uiButton.secondaryText}>정보 제보</Text>
              </Pressable>
            </View>
          ) : null}

          <View style={styles.resultHeader}>
            <Text style={styles.resultTitle}>
              {submittedQuery ? `'${submittedQuery}' 결과` : "검색 결과"}
            </Text>
            <Text style={styles.resultCount}>{places.length}곳</Text>
          </View>

          {status === "loading" ? (
            <View style={styles.stateBox}>
              <ActivityIndicator color={Palette.accent} />
              <Text style={styles.stateText}>장소를 찾고 있습니다.</Text>
            </View>
          ) : message ? (
            <View style={styles.stateBox}>
              <Text style={styles.stateText}>{message}</Text>
            </View>
          ) : (
            <View style={styles.resultList}>
              {places.map((place, index) => {
                const selected = selectedPlace?.id === place.id;
                return (
                  <Pressable
                    key={`${place.result_source}-${place.id}`}
                    onPress={() => setSelectedPlace(place)}
                    style={[
                      styles.resultCard,
                      selected && styles.resultCardSelected,
                    ]}
                  >
                    <View
                      style={[
                        styles.resultNumber,
                        selected && styles.resultNumberSelected,
                      ]}
                    >
                      <Text
                        style={[
                          styles.resultNumberText,
                          selected && styles.resultNumberTextSelected,
                        ]}
                      >
                        {index + 1}
                      </Text>
                    </View>
                    <View style={styles.resultCopy}>
                      <View style={styles.resultNameRow}>
                        <Text numberOfLines={1} style={styles.resultName}>
                          {place.name}
                        </Text>
                        <Text style={styles.resultDistance}>
                          {formatDistance(place.distance)}
                        </Text>
                      </View>
                      <Text numberOfLines={1} style={styles.resultMeta}>
                        {place.category_label || place.category} ·{" "}
                        {place.address || "주소 정보 없음"}
                      </Text>
                      {place.tags?.length ? (
                        <View style={styles.tags}>
                          {place.tags.slice(0, 3).map((tag) => (
                            <Text
                              key={`${place.id}-${tag.id ?? tag.name}`}
                              style={styles.tag}
                            >
                              {tag.name}
                            </Text>
                          ))}
                        </View>
                      ) : null}
                    </View>
                  </Pressable>
                );
              })}
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
      <BottomNav />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#F5F7F6" },
  safeArea: { flex: 1 },
  content: {
    width: "100%",
    maxWidth: 760,
    alignSelf: "center",
    padding: Spacing.four,
    paddingBottom: BottomTabInset + Spacing.six,
    gap: Spacing.three,
  },
  header: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
  },
  kicker: {
    color: Palette.accent,
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 1.5,
  },
  title: {
    marginTop: 6,
    color: Palette.ink,
    fontSize: 30,
    fontWeight: "900",
    letterSpacing: -0.7,
  },
  baseLocation: { color: Palette.muted, fontSize: 11, fontWeight: "700" },
  searchBox: {
    marginTop: 10,
    padding: 5,
    flexDirection: "row",
    borderRadius: 15,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  searchInput: {
    minWidth: 0,
    flex: 1,
    height: 50,
    paddingHorizontal: 14,
    color: Palette.ink,
    fontSize: 14,
  },
  searchButton: {
    minWidth: 68,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: Palette.accent,
  },
  searchButtonLabel: { color: "#FFFFFF", fontSize: 13, fontWeight: "800" },
  filters: { gap: 8, paddingVertical: 2, paddingRight: Spacing.four },
  filter: {
    paddingHorizontal: 15,
    paddingVertical: 9,
    borderWidth: 1,
    borderColor: "#DFE5E2",
    borderRadius: Radius.pill,
    backgroundColor: Palette.surface,
  },
  filterActive: { borderColor: Palette.ink, backgroundColor: Palette.ink },
  filterLabel: { color: Palette.muted, fontSize: 12, fontWeight: "700" },
  filterLabelActive: { color: Palette.surface },
  mapSection: {
    overflow: "hidden",
    borderRadius: Radius.large,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  selectedSummary: {
    padding: 15,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  selectedCopy: { minWidth: 0, flex: 1 },
  selectedName: { color: Palette.ink, fontSize: 15, fontWeight: "900" },
  selectedAddress: { marginTop: 4, color: Palette.muted, fontSize: 11 },
  routeButton: {
    paddingHorizontal: 13,
    paddingVertical: 10,
    borderRadius: Radius.small,
    backgroundColor: Palette.accentSoft,
  },
  routeButtonLabel: { color: Palette.accent, fontSize: 11, fontWeight: "900" },
  placeActions: { flexDirection: "row", gap: 8 },
  resultHeader: {
    marginTop: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  resultTitle: { color: Palette.ink, fontSize: 18, fontWeight: "900" },
  resultCount: { color: Palette.muted, fontSize: 12, fontWeight: "700" },
  stateBox: {
    minHeight: 140,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
  },
  stateText: { color: Palette.muted, fontSize: 13 },
  resultList: { gap: 9 },
  resultCard: {
    padding: 14,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12,
    borderWidth: 1,
    borderColor: "#E3E8E5",
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
  },
  resultCardSelected: {
    borderColor: Palette.accent,
    backgroundColor: "#F7FBFA",
  },
  resultNumber: {
    width: 30,
    height: 30,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 15,
    backgroundColor: "#EEF2F0",
  },
  resultNumberSelected: { backgroundColor: Palette.accent },
  resultNumberText: { color: Palette.muted, fontSize: 11, fontWeight: "900" },
  resultNumberTextSelected: { color: "#FFFFFF" },
  resultCopy: { minWidth: 0, flex: 1 },
  resultNameRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  resultName: {
    minWidth: 0,
    flex: 1,
    color: Palette.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  resultDistance: { color: Palette.accent, fontSize: 11, fontWeight: "800" },
  resultMeta: { marginTop: 5, color: Palette.muted, fontSize: 11 },
  tags: { marginTop: 9, flexDirection: "row", flexWrap: "wrap", gap: 5 },
  tag: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    overflow: "hidden",
    borderRadius: Radius.pill,
    backgroundColor: "#EEF2F0",
    color: "#52605A",
    fontSize: 10,
    fontWeight: "700",
  },
  pressed: { opacity: 0.65 },
});

const uiButton = StyleSheet.create({
  secondary: {
    flex: 1,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#DCE3DF",
    borderRadius: Radius.small,
    backgroundColor: Palette.surface,
  },
  secondaryText: { color: Palette.ink, fontSize: 12, fontWeight: "800" },
});
