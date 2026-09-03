import { router } from "expo-router";
import { useEffect, useState } from "react";
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

import { searchMapPlaces } from "@/api/recommendations";
import { BottomNav } from "@/components/bottom-nav";
import {
  BottomTabInset,
  Palette,
  Radius,
  Shadow,
  Spacing,
} from "@/constants/theme";
import type { Place } from "@/types/place";

const CATEGORIES = [
  { label: "주차장", query: "무료 주차장", symbol: "P" },
  { label: "화장실", query: "공중화장실", symbol: "WC" },
  { label: "공원", query: "공원", symbol: "休" },
  { label: "쉼터", query: "무더위 쉼터", symbol: "涼" },
] as const;

const formatDistance = (distance?: number) => {
  if (distance === undefined) return "";
  return distance < 1000
    ? `${Math.round(distance)}m`
    : `${(distance / 1000).toFixed(1)}km`;
};

export default function HomeScreen() {
  const [query, setQuery] = useState("");
  const [placeQuery, setPlaceQuery] = useState("");
  const [nearbyPlaces, setNearbyPlaces] = useState<Place[]>([]);
  const [loading, setLoading] = useState(true);
  const [nearbyError, setNearbyError] = useState("");
  const [nearbyReloadKey, setNearbyReloadKey] = useState(0);

  const openRecommendation = (nextQuery = query) => {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;
    router.push({ pathname: "/recommend", params: { q: trimmed } });
  };

  const openPlaceSearch = (nextQuery = placeQuery) => {
    const trimmed = nextQuery.trim();
    router.push({
      pathname: "/explore",
      params: trimmed ? { q: trimmed } : {},
    });
  };

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    searchMapPlaces({ query: "공원", limit: 3, signal: controller.signal })
      .then((data) => {
        if (active) setNearbyPlaces(data.results);
      })
      .catch((error) => {
        if (!active || error?.name === "AbortError") return;
        setNearbyPlaces([]);
        setNearbyError(
          error instanceof Error
            ? error.message
            : "주변 장소를 불러오지 못했습니다.",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [nearbyReloadKey]);

  return (
    <View style={styles.screen}>
      <SafeAreaView style={styles.safeArea} edges={["top", "left", "right"]}>
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.header}>
            <Text style={styles.brand}>LIFE MAP</Text>
            <Text style={styles.location}>서울시청 기준</Text>
          </View>

          <View style={styles.hero}>
            <Text style={styles.title}>
              지금 상황에 맞는 장소를{`\n`}이유와 함께.
            </Text>
            <Text style={styles.description}>
              원하는 분위기와 조건을 말하면 근거를 확인해 추천합니다.
            </Text>
            <View style={styles.searchBox}>
              <TextInput
                value={query}
                onChangeText={setQuery}
                onSubmitEditing={() => openRecommendation()}
                placeholder="예: 조용히 오래 작업할 수 있는 카페"
                placeholderTextColor="#8A918E"
                returnKeyType="search"
                style={styles.searchInput}
              />
              <Pressable
                accessibilityRole="button"
                disabled={!query.trim()}
                onPress={() => openRecommendation()}
                style={({ pressed }) => [
                  styles.searchButton,
                  !query.trim() && styles.buttonDisabled,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.searchButtonLabel}>찾기</Text>
              </Pressable>
            </View>
          </View>

          <View style={styles.placeSearchCard}>
            <View>
              <Text style={styles.placeSearchTitle}>일반 장소 검색</Text>
              <Text style={styles.placeSearchDescription}>
                장소명이나 업종을 가까운 순서로 빠르게 찾습니다.
              </Text>
            </View>
            <View style={styles.placeSearchBox}>
              <TextInput
                value={placeQuery}
                onChangeText={setPlaceQuery}
                onSubmitEditing={() => openPlaceSearch()}
                placeholder="예: 서면역 약국, 광안리 주차장"
                placeholderTextColor="#8A918E"
                returnKeyType="search"
                style={styles.placeSearchInput}
              />
              <Pressable
                onPress={() => openPlaceSearch()}
                style={styles.placeSearchButton}
              >
                <Text style={styles.placeSearchButtonLabel}>일반 검색</Text>
              </Pressable>
            </View>
          </View>

          <View>
            <Text style={styles.sectionLabel}>빠른 탐색</Text>
            <View style={styles.categoryGrid}>
              {CATEGORIES.map((item) => (
                <Pressable
                  key={item.label}
                  onPress={() => openPlaceSearch(item.query)}
                  style={styles.categoryCard}
                >
                  <View style={styles.categorySymbol}>
                    <Text style={styles.categorySymbolText}>{item.symbol}</Text>
                  </View>
                  <Text style={styles.categoryLabel}>{item.label}</Text>
                </Pressable>
              ))}
            </View>
          </View>

          <View>
            <View style={styles.sectionHeader}>
              <View>
                <Text style={styles.sectionLabel}>주변 공원</Text>
                <Text style={styles.sectionCaption}>
                  서버에서 불러온 가까운 장소
                </Text>
              </View>
              <Pressable onPress={() => openPlaceSearch("공원")}>
                <Text style={styles.more}>전체 보기</Text>
              </Pressable>
            </View>
            {loading ? (
              <View style={styles.loading}>
                <ActivityIndicator color={Palette.accent} />
              </View>
            ) : nearbyError ? (
              <View style={styles.loadError}>
                <Text style={styles.loadErrorText}>{nearbyError}</Text>
                <Pressable
                  onPress={() => {
                    setLoading(true);
                    setNearbyError("");
                    setNearbyReloadKey((value) => value + 1);
                  }}
                  style={styles.retryButton}
                >
                  <Text style={styles.retryButtonLabel}>다시 시도</Text>
                </Pressable>
              </View>
            ) : (
              <View style={styles.placeList}>
                {nearbyPlaces.map((place, index) => (
                  <Pressable
                    key={place.id}
                    onPress={() =>
                      router.push({
                        pathname: "/explore",
                        params: { q: "공원", placeId: String(place.id) },
                      })
                    }
                    style={({ pressed }) => [
                      styles.placeRow,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={styles.placeIndex}>
                      {String(index + 1).padStart(2, "0")}
                    </Text>
                    <View style={styles.placeCopy}>
                      <Text numberOfLines={1} style={styles.placeName}>
                        {place.name}
                      </Text>
                      <Text numberOfLines={1} style={styles.placeAddress}>
                        {place.address || place.category_label}
                      </Text>
                    </View>
                    <Text style={styles.distance}>
                      {formatDistance(place.distance)}
                    </Text>
                  </Pressable>
                ))}
              </View>
            )}
          </View>
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
    gap: 38,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  brand: {
    color: Palette.ink,
    fontSize: 15,
    fontWeight: "900",
    letterSpacing: 1.8,
  },
  location: { color: Palette.muted, fontSize: 12, fontWeight: "700" },
  hero: { paddingTop: Spacing.four },
  title: {
    color: "#17201D",
    fontSize: 38,
    lineHeight: 48,
    fontWeight: "900",
    letterSpacing: -1.3,
  },
  description: {
    maxWidth: 480,
    marginTop: 14,
    color: Palette.muted,
    fontSize: 14,
    lineHeight: 22,
  },
  searchBox: {
    marginTop: Spacing.four,
    padding: 5,
    flexDirection: "row",
    borderRadius: 15,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  searchInput: {
    minWidth: 0,
    flex: 1,
    height: 52,
    paddingHorizontal: 15,
    color: Palette.ink,
    fontSize: 15,
  },
  searchButton: {
    minWidth: 72,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: Palette.accent,
  },
  searchButtonLabel: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  buttonDisabled: { opacity: 0.45 },
  placeSearchCard: {
    padding: 16,
    gap: 12,
    borderWidth: 1,
    borderColor: "#DCE5E1",
    borderRadius: Radius.medium,
    backgroundColor: "#F8FBFA",
  },
  placeSearchTitle: { color: Palette.ink, fontSize: 15, fontWeight: "900" },
  placeSearchDescription: {
    marginTop: 5,
    color: Palette.muted,
    fontSize: 11,
    lineHeight: 17,
  },
  placeSearchBox: { flexDirection: "row", gap: 8 },
  placeSearchInput: {
    minWidth: 0,
    height: 44,
    paddingHorizontal: 13,
    flex: 1,
    borderWidth: 1,
    borderColor: "#D2DDD8",
    borderRadius: Radius.small,
    backgroundColor: Palette.surface,
    color: Palette.ink,
    fontSize: 12,
  },
  placeSearchButton: {
    minWidth: 78,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.small,
    backgroundColor: Palette.accent,
  },
  placeSearchButtonLabel: { color: "#FFFFFF", fontSize: 11, fontWeight: "900" },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
  },
  sectionLabel: { color: Palette.ink, fontSize: 18, fontWeight: "900" },
  sectionCaption: { marginTop: 5, color: Palette.muted, fontSize: 12 },
  more: { color: Palette.accent, fontSize: 12, fontWeight: "800" },
  categoryGrid: { marginTop: 14, flexDirection: "row", gap: 9 },
  categoryCard: {
    flex: 1,
    minWidth: 0,
    paddingVertical: 15,
    alignItems: "center",
    gap: 9,
    borderWidth: 1,
    borderColor: "#E4E9E6",
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
  },
  categorySymbol: {
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 12,
    backgroundColor: Palette.accentSoft,
  },
  categorySymbolText: {
    color: Palette.accent,
    fontSize: 11,
    fontWeight: "900",
  },
  categoryLabel: { color: Palette.ink, fontSize: 12, fontWeight: "800" },
  loading: { height: 130, alignItems: "center", justifyContent: "center" },
  loadError: {
    height: 130,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  loadErrorText: { color: Palette.muted, fontSize: 12 },
  retryButton: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: Radius.small,
    backgroundColor: Palette.accent,
  },
  retryButtonLabel: { color: "#FFFFFF", fontSize: 12, fontWeight: "800" },
  placeList: {
    marginTop: 13,
    overflow: "hidden",
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
  },
  placeRow: {
    minHeight: 72,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 13,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Palette.border,
  },
  placeIndex: { color: Palette.accent, fontSize: 11, fontWeight: "900" },
  placeCopy: { minWidth: 0, flex: 1 },
  placeName: { color: Palette.ink, fontSize: 14, fontWeight: "800" },
  placeAddress: { marginTop: 5, color: Palette.muted, fontSize: 11 },
  distance: { color: Palette.ink, fontSize: 12, fontWeight: "700" },
  pressed: { opacity: 0.65 },
});
