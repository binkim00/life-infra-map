import { router, useLocalSearchParams } from "expo-router";
import * as Location from "expo-location";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
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
import { PlaceDetailSheet } from "@/components/place-detail-sheet";
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
  { label: "흡연구역", query: "흡연구역" },
] as const;

const RADIUS_OPTIONS = [
  { label: "1km", value: 1000 },
  { label: "3km", value: 3000 },
  { label: "5km", value: 5000 },
  { label: "10km", value: 10000 },
] as const;

const NEARBY_CATEGORY_QUERIES = new Set([
  "주차장",
  "공영주차장",
  "화장실",
  "공중화장실",
  "개방화장실",
  "공원",
  "쉼터",
  "무더위쉼터",
  "흡연구역",
  "흡연실",
  "카페",
  "커피",
  "식당",
  "음식점",
  "맛집",
  "약국",
  "병원",
  "편의점",
  "마트",
  "주유소",
  "지하철역",
  "기차역",
]);

const isNearbyCategoryQuery = (value: string) => {
  // 특정 지역·장소가 없는 업종/조건 검색만 현재 위치 반경을 사용합니다.
  // 목록에 없는 고유명사는 명시적인 장소명으로 보고 전국 검색합니다.
  const normalized = value.replace(/\s+/g, "").trim();
  const withoutGenericConditions = normalized.replace(
    /(내주변|주변|근처|가까운|가까이|무료|유료|24시간|늦게까지|지금여는|영업중|조용한|넓은|쾌적한|저렴한|가성비좋은|아이와|가족과|혼자|데이트|갈만한|가기좋은|이용가능한|주차가능한|반려동물동반)/g,
    "",
  );
  return NEARBY_CATEGORY_QUERIES.has(withoutGenericConditions);
};

const formatDistance = (distance?: number) =>
  distance === undefined
    ? "거리 정보 없음"
    : distance < 1000
      ? `${Math.round(distance)}m`
      : `${(distance / 1000).toFixed(1)}km`;

export default function ExploreScreen() {
  const { requireLogin, isLoggedIn } = useAuth();
  const params = useLocalSearchParams<{
    q?: string;
    placeId?: string;
    lat?: string;
    lng?: string;
  }>();
  const initialQuery = typeof params.q === "string" ? params.q : "";
  const initialLat = Number(params.lat);
  const initialLng = Number(params.lng);
  const hasInitialCenter =
    Number.isFinite(initialLat) && Number.isFinite(initialLng);
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);
  const [searchRequestId, setSearchRequestId] = useState(initialQuery ? 1 : 0);
  const [places, setPlaces] = useState<Place[]>([]);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [detailPlace, setDetailPlace] = useState<Place | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [radius, setRadius] = useState(3000);
  const [mapCenter, setMapCenter] = useState<{
    lat: number;
    lng: number;
  } | null>(null);
  const [searchCenterOverride, setSearchCenterOverride] = useState<{
    lat: number;
    lng: number;
  } | null>(null);
  const [locationStatus, setLocationStatus] = useState<
    "requesting" | "ready" | "unavailable"
  >(hasInitialCenter ? "ready" : "requesting");
  const [status, setStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >(initialQuery ? "loading" : "idle");
  const [message, setMessage] = useState("");
  const [center, setCenter] = useState<{
    lat: number | null;
    lng: number | null;
    label: string;
  }>({
    lat: hasInitialCenter ? initialLat : null,
    lng: hasInitialCenter ? initialLng : null,
    label: hasInitialCenter ? "현재 위치" : "위치 확인 중",
  });

  const requestCurrentLocation = useCallback(async (showError = true) => {
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) {
        setLocationStatus("unavailable");
        setCenter({ lat: null, lng: null, label: "위치 권한 필요" });
        if (showError) {
          setStatus("error");
          setMessage("주변 검색을 사용하려면 현재 위치 권한을 허용해 주세요.");
        }
        return false;
      }
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      setCenter({
        lat: position.coords.latitude,
        lng: position.coords.longitude,
        label: "현재 위치",
      });
      setLocationStatus("ready");
      setMessage("");
      return true;
    } catch {
      setLocationStatus("unavailable");
      setCenter({ lat: null, lng: null, label: "위치 확인 실패" });
      if (showError) {
        setStatus("error");
        setMessage(
          "현재 위치를 확인하지 못했습니다. 위치 설정을 확인해 주세요.",
        );
      }
      return false;
    }
  }, []);

  useEffect(() => {
    if (hasInitialCenter) return;
    const timer = setTimeout(() => void requestCurrentLocation(true), 0);
    return () => clearTimeout(timer);
  }, [hasInitialCenter, requestCurrentLocation]);

  const runSearch = useCallback(
    (
      nextQuery = query,
      searchCenter: { lat: number; lng: number } | null = null,
    ) => {
      const trimmed = nextQuery.trim();
      if (!trimmed) {
        setMessage("검색어를 입력하거나 시설 종류를 선택하세요.");
        return;
      }
      setQuery(trimmed);
      setStatus("loading");
      setMessage("");
      setSubmittedQuery(trimmed);
      setSearchCenterOverride(searchCenter);
      // 같은 검색어를 다시 눌러도 실제 요청을 새로 보냅니다.
      setSearchRequestId((value) => value + 1);
    },
    [query],
  );

  const resetSearch = () => {
    setQuery("");
    setSubmittedQuery("");
    setPlaces([]);
    setSelectedPlace(null);
    setSearchCenterOverride(null);
    setMessage("");
    setStatus("idle");
  };

  useEffect(() => {
    if (!submittedQuery || !searchRequestId) return;
    const nearbyCategorySearch = isNearbyCategoryQuery(submittedQuery);
    if (
      nearbyCategorySearch &&
      !searchCenterOverride &&
      locationStatus === "requesting"
    )
      return;
    const searchAroundCenter = Boolean(
      searchCenterOverride || nearbyCategorySearch,
    );
    const controller = new AbortController();
    searchMapPlaces({
      query: submittedQuery,
      lat:
        searchCenterOverride?.lat ?? (nearbyCategorySearch ? center.lat : null),
      lng:
        searchCenterOverride?.lng ?? (nearbyCategorySearch ? center.lng : null),
      radius: searchAroundCenter ? radius : undefined,
      signal: controller.signal,
    })
      .then((data) => {
        setPlaces(data.results);
        const requested = data.results.find(
          (place) => String(place.id) === params.placeId,
        );
        setSelectedPlace(requested || data.results[0] || null);
        setStatus("success");
        setMessage("");
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
            data.message ||
              "조건에 맞는 장소가 없습니다. 다른 검색어를 입력해 보세요.",
          );
      })
      .catch((error) => {
        if (controller.signal.aborted || error?.name === "AbortError") return;
        setPlaces([]);
        setSelectedPlace(null);
        setStatus("error");
        setMessage(
          error instanceof Error ? error.message : "서버에 연결할 수 없습니다.",
        );
      });
    return () => controller.abort();
  }, [
    submittedQuery,
    searchRequestId,
    params.placeId,
    center.lat,
    center.lng,
    radius,
    isLoggedIn,
    locationStatus,
    searchCenterOverride,
  ]);

  const openPlaceDetails = (place: Place) => {
    setSelectedPlace(place);
    setDetailPlace(place);
    setDetailVisible(true);
  };

  const reportSelectedPlace = () => {
    if (!detailPlace || !requireLogin()) return;
    setDetailVisible(false);
    router.push({
      pathname: "/place-report",
      params: {
        placeId: String(detailPlace.id),
        name: detailPlace.name,
        address: detailPlace.address || "",
        lat: String(detailPlace.lat),
        lng: String(detailPlace.lng),
      },
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
  const usesNearbyRadius =
    !submittedQuery || isNearbyCategoryQuery(submittedQuery);
  const currentMapLocation = useMemo(
    () =>
      usesNearbyRadius && center.lat !== null && center.lng !== null
        ? { lat: center.lat, lng: center.lng }
        : null,
    [center.lat, center.lng, usesNearbyRadius],
  );

  return (
    <View style={styles.screen}>
      <View style={styles.mapCanvas}>
        <PlaceMap
          expanded
          place={selectedPlace}
          places={places}
          displayMode="overview"
          onSelectPlace={setSelectedPlace}
          onCenterChange={setMapCenter}
          currentLocation={currentMapLocation}
        />
        {!selectedPlace && !currentMapLocation ? (
          <View pointerEvents="none" style={styles.fullMapPlaceholder}>
            <Text style={styles.mapPlaceholderTitle}>
              {locationStatus === "requesting"
                ? "현재 위치를 확인하고 있습니다."
                : "지도를 표시할 위치가 필요합니다."}
            </Text>
            <Text style={styles.mapPlaceholderText}>
              위치 권한을 허용하거나 지역과 시설을 검색해 주세요.
            </Text>
          </View>
        ) : null}
      </View>

      <SafeAreaView
        pointerEvents="box-none"
        style={styles.mapOverlay}
        edges={["top", "left", "right"]}
      >
        <View style={styles.searchControls}>
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

          <View style={styles.filterRow}>
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
                      filter.query ? runSearch(filter.query) : resetSearch()
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
            <Pressable
              onPress={() => void requestCurrentLocation()}
              style={styles.locationPill}
            >
              <View
                style={[
                  styles.locationDot,
                  locationStatus === "ready" && styles.locationDotReady,
                ]}
              />
              <Text style={styles.baseLocation}>내 위치</Text>
            </Pressable>
          </View>

          {usesNearbyRadius ? (
            <View style={styles.radiusBar}>
              <Text style={styles.scopeLabel}>주변 범위</Text>
              <View style={styles.radiusOptions}>
                {RADIUS_OPTIONS.map((option) => (
                  <Pressable
                    key={option.value}
                    onPress={() => setRadius(option.value)}
                    style={[
                      styles.radiusOption,
                      radius === option.value && styles.radiusOptionActive,
                    ]}
                  >
                    <Text
                      style={[
                        styles.radiusText,
                        radius === option.value && styles.radiusTextActive,
                      ]}
                    >
                      {option.label}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}
          {submittedQuery && mapCenter ? (
            <Pressable
              onPress={() => runSearch(submittedQuery, mapCenter)}
              style={styles.mapResearchButton}
            >
              <Text style={styles.mapResearchButtonText}>
                현재 지도에서 재검색
              </Text>
            </Pressable>
          ) : null}
        </View>
      </SafeAreaView>

      <View style={styles.resultSheet}>
        <View style={styles.sheetHandle} />
        {selectedPlace ? (
          <View style={styles.selectedSummary}>
            <View style={styles.selectedNumber}>
              <Text style={styles.selectedNumberText}>
                {places.findIndex(
                  (item) => String(item.id) === String(selectedPlace.id),
                ) + 1}
              </Text>
            </View>
            <View style={styles.selectedCopy}>
              <Text numberOfLines={1} style={styles.selectedName}>
                {selectedPlace.name}
              </Text>
              <Text numberOfLines={1} style={styles.selectedAddress}>
                {selectedPlace.address || selectedPlace.category_label}
              </Text>
            </View>
            <Pressable
              onPress={() => openPlaceDetails(selectedPlace)}
              style={styles.routeButton}
            >
              <Text style={styles.routeButtonLabel}>상세보기</Text>
            </Pressable>
          </View>
        ) : null}

        <View style={styles.resultHeader}>
          <Text style={styles.resultTitle}>
            {submittedQuery ? `'${submittedQuery}' 결과` : "주변 장소 검색"}
          </Text>
          <Text style={styles.resultCount}>
            {places.length ? `${places.length}곳` : ""}
          </Text>
        </View>

        {status === "loading" ? (
          <View style={styles.compactStateBox}>
            <ActivityIndicator color={Palette.accent} />
            <Text style={styles.stateText}>장소를 찾고 있습니다.</Text>
          </View>
        ) : message ? (
          <View style={styles.compactStateBox}>
            <Text style={styles.stateText}>{message}</Text>
          </View>
        ) : status === "idle" ? (
          <View style={styles.compactStateBox}>
            <Text style={styles.stateText}>
              검색하거나 위의 빠른 필터를 선택해 보세요.
            </Text>
          </View>
        ) : (
          <ScrollView
            horizontal
            keyboardShouldPersistTaps="handled"
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.horizontalResults}
          >
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
                      {place.category_label || place.category}
                    </Text>
                  </View>
                </Pressable>
              );
            })}
          </ScrollView>
        )}
      </View>
      <PlaceDetailSheet
        place={detailPlace}
        visible={detailVisible}
        onClose={() => setDetailVisible(false)}
        onSave={saveSelectedPlace}
        onReport={reportSelectedPlace}
      />
      <BottomNav />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#F5F7F6" },
  mapCanvas: { position: "absolute", inset: 0, backgroundColor: Palette.map },
  mapOverlay: { position: "absolute", inset: 0, justifyContent: "flex-start" },
  searchControls: {
    width: "100%",
    maxWidth: 760,
    alignSelf: "center",
    paddingHorizontal: 12,
    paddingTop: 8,
    gap: 8,
  },
  filterRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  radiusBar: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 6,
    paddingLeft: 12,
    borderRadius: Radius.pill,
    backgroundColor: "rgba(255,255,255,0.96)",
    boxShadow: Shadow.card,
  },
  mapResearchButton: {
    alignSelf: "center",
    minHeight: 38,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(15,118,110,0.22)",
    borderRadius: Radius.pill,
    backgroundColor: "rgba(255,255,255,0.97)",
    boxShadow: Shadow.card,
  },
  mapResearchButtonText: {
    color: Palette.accent,
    fontSize: 12,
    fontWeight: "900",
  },
  resultSheet: {
    position: "absolute",
    left: 12,
    right: 12,
    bottom: 96,
    maxWidth: 736,
    alignSelf: "center",
    paddingTop: 8,
    paddingBottom: 12,
    borderWidth: 1,
    borderColor: "#E1E6E3",
    borderRadius: Radius.large,
    backgroundColor: "rgba(255,255,255,0.98)",
    boxShadow: Shadow.card,
  },
  sheetHandle: {
    width: 36,
    height: 4,
    alignSelf: "center",
    marginBottom: 5,
    borderRadius: 2,
    backgroundColor: "#CFD8D4",
  },
  horizontalResults: { gap: 8, paddingHorizontal: 12, paddingBottom: 2 },
  compactStateBox: {
    minHeight: 54,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
    paddingHorizontal: 16,
  },
  fullMapPlaceholder: {
    position: "absolute",
    inset: 0,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: Palette.map,
  },
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
  locationPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: Radius.pill,
    backgroundColor: "rgba(255,255,255,0.96)",
    boxShadow: Shadow.card,
  },
  locationDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: "#A7B0AC",
  },
  locationDotReady: { backgroundColor: Palette.accent },
  baseLocation: { color: Palette.muted, fontSize: 11, fontWeight: "800" },
  searchBox: {
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
  filters: { gap: 8, paddingVertical: 2, paddingRight: 4 },
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
  scopeRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  scopeLabel: { color: Palette.muted, fontSize: 11, fontWeight: "800" },
  globalScopeText: { color: Palette.accent, fontSize: 11, fontWeight: "800" },
  radiusOptions: { flexDirection: "row", gap: 6 },
  radiusOption: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: Radius.pill,
    backgroundColor: "#E9EFEC",
  },
  radiusOptionActive: { backgroundColor: Palette.accent },
  radiusText: { color: Palette.muted, fontSize: 10, fontWeight: "800" },
  radiusTextActive: { color: "#FFFFFF" },
  mapSection: {
    overflow: "hidden",
    borderRadius: Radius.large,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  mapExpandButton: {
    position: "absolute",
    top: 12,
    right: 12,
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderRadius: Radius.pill,
    backgroundColor: "rgba(255,255,255,0.94)",
    boxShadow: Shadow.card,
  },
  mapExpandButtonLabel: { color: Palette.ink, fontSize: 11, fontWeight: "900" },
  mapPlaceholder: {
    position: "absolute",
    inset: 0,
    height: 390,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: Radius.large,
    backgroundColor: Palette.map,
  },
  mapPlaceholderTitle: {
    color: Palette.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  mapPlaceholderText: {
    color: Palette.muted,
    fontSize: 12,
    textAlign: "center",
  },
  selectedSummary: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  selectedCopy: { minWidth: 0, flex: 1 },
  selectedName: { color: Palette.ink, fontSize: 15, fontWeight: "900" },
  selectedAddress: { marginTop: 4, color: Palette.muted, fontSize: 11 },
  mapModal: { flex: 1, backgroundColor: Palette.surface },
  mapModalHeader: {
    paddingHorizontal: Spacing.four,
    paddingVertical: Spacing.three,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#E3E8E5",
  },
  selectedNumber: {
    width: 32,
    height: 32,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 16,
    backgroundColor: Palette.accent,
  },
  selectedNumberText: { color: "#FFFFFF", fontSize: 11, fontWeight: "900" },
  mapModalTitleCopy: { minWidth: 0, flex: 1 },
  mapModalTitle: { color: Palette.ink, fontSize: 18, fontWeight: "900" },
  mapModalSubtitle: { marginTop: 3, color: Palette.muted, fontSize: 11 },
  mapCloseButton: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: Radius.pill,
    backgroundColor: "#EEF2F0",
  },
  mapCloseButtonLabel: { color: Palette.ink, fontSize: 12, fontWeight: "800" },
  expandedMapBody: { flex: 1, backgroundColor: Palette.map },
  mapModalPlace: {
    padding: Spacing.four,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderTopWidth: 1,
    borderTopColor: "#E3E8E5",
    backgroundColor: Palette.surface,
  },
  routeButton: {
    paddingHorizontal: 13,
    paddingVertical: 10,
    borderRadius: Radius.small,
    backgroundColor: Palette.accentSoft,
  },
  routeButtonLabel: { color: Palette.accent, fontSize: 11, fontWeight: "900" },
  resultHeader: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  resultTitle: { color: Palette.ink, fontSize: 13, fontWeight: "900" },
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
    width: 238,
    padding: 11,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12,
    borderWidth: 1,
    borderColor: "#E3E8E5",
    borderRadius: Radius.small,
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
