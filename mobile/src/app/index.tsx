import { router } from "expo-router";
import { searchLocation } from "@/utils/location";
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
  { label: "카페", query: "카페", symbol: "☕" },
  { label: "식당", query: "식당", symbol: "●" },
  { label: "주차", query: "무료 주차장", symbol: "P" },
  { label: "화장실", query: "공중화장실", symbol: "WC" },
  { label: "공원", query: "공원", symbol: "♣" },
  { label: "쉼터", query: "무더위 쉼터", symbol: "休" },
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
  const [nearbyCenter, setNearbyCenter] = useState<{
    lat: number;
    lng: number;
  } | null>(null);

  const openRecommendation = (nextQuery = query) => {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;
    router.push({
      pathname: "/recommend",
      params: {
        q: trimmed,
        lat: nearbyCenter ? String(nearbyCenter.lat) : undefined,
        lng: nearbyCenter ? String(nearbyCenter.lng) : undefined,
      },
    });
  };

  const openPlaceSearch = (nextQuery = placeQuery) => {
    const trimmed = nextQuery.trim();
    router.push({
      pathname: "/explore",
      params: {
        q: trimmed || undefined,
        lat: nearbyCenter ? String(nearbyCenter.lat) : undefined,
        lng: nearbyCenter ? String(nearbyCenter.lng) : undefined,
      },
    });
  };

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const loadNearbyParks = async () => {
      const coordinates = await searchLocation();
      if (!coordinates) {
        throw new Error(
          "주변 공원을 보려면 위치 권한이 필요합니다. 권한을 허용한 뒤 다시 시도해 주세요.",
        );
      }
      const nextCenter = {
        lat: coordinates.latitude,
        lng: coordinates.longitude,
      };
      if (active) setNearbyCenter(nextCenter);
      return searchMapPlaces({
        query: "공원",
        lat: nextCenter.lat,
        lng: nextCenter.lng,
        limit: 6,
        signal: controller.signal,
      });
    };

    loadNearbyParks()
      .then((data) => {
        if (active) {
          setNearbyPlaces(data.results);
          setNearbyError(data.message || "");
        }
      })
      .catch((error) => {
        if (!active || error?.name === "AbortError") return;
        setNearbyPlaces([]);
        setNearbyCenter(null);
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
            <View style={styles.brandRow}>
              <View style={styles.brandMark}><Text style={styles.brandMarkText}>⌖</Text></View>
              <View>
                <Text style={styles.brand}>여기일지도</Text>
                <Text style={styles.brandCaption}>LIFE MAP</Text>
              </View>
            </View>
            <Pressable
              accessibilityLabel="알림 보기"
              accessibilityRole="button"
              onPress={() => router.push("/notifications")}
              style={({ pressed }) => [styles.headerButton, pressed && styles.pressed]}
            >
              <Text style={styles.headerButtonText}>♢</Text>
            </Pressable>
          </View>

          <View style={styles.hero}>
            <Text style={styles.title}>
              오늘 어디로 갈까요?
            </Text>
            <Text style={styles.description}>
              상황과 조건을 말하면 확인할 수 있는 근거와 함께 추천해요.
            </Text>
            <View style={styles.searchBox}>
              <TextInput
                value={query}
                onChangeText={setQuery}
                onSubmitEditing={() => openRecommendation()}
                placeholder="예: 조용히 오래 작업할 수 있는 카페"
                placeholderTextColor="#5F6863"
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
                <Text style={styles.searchButtonLabel}>추천받기</Text>
              </Pressable>
            </View>
          </View>

          <View style={styles.placeSearchCard}>
            <View>
              <View style={styles.searchTitleRow}>
                <View style={styles.searchIcon}><Text style={styles.searchIconText}>⌕</Text></View>
                <Text style={styles.placeSearchTitle}>일반 장소 검색</Text>
              </View>
              <Text style={styles.placeSearchDescription}>
                장소명이나 지역·업종을 빠르게 찾습니다.
              </Text>
            </View>
            <View style={styles.placeSearchBox}>
              <TextInput
                value={placeQuery}
                onChangeText={setPlaceQuery}
                onSubmitEditing={() => openPlaceSearch()}
                placeholder="예: 서면역 약국, 광안리 주차장"
                placeholderTextColor="#5F6863"
                returnKeyType="search"
                style={styles.placeSearchInput}
              />
              <Pressable
                onPress={() => openPlaceSearch()}
                style={styles.placeSearchButton}
              >
                <Text style={styles.placeSearchButtonLabel}>검색</Text>
              </Pressable>
            </View>
          </View>

          <View>
            <Text style={styles.sectionLabel}>함께 만드는 지도</Text>
            <Text style={styles.sectionCaption}>장소 이야기를 나누고, 빠진 정보를 알려주세요.</Text>
            <View style={styles.serviceGrid}>
              <Pressable
                accessibilityRole="button"
                onPress={() => router.push("/boards/free")}
                style={({ pressed }) => [styles.serviceCard, pressed && styles.pressed]}
              >
                <Text style={styles.serviceSymbol}>☵</Text>
                <View style={styles.serviceCopy}>
                  <Text style={styles.serviceTitle}>커뮤니티</Text>
                  <Text style={styles.serviceText}>장소 팁과 이야기를 나눠요</Text>
                </View>
                <Text style={styles.serviceArrow}>›</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={() => router.push("/place-report")}
                style={({ pressed }) => [styles.serviceCard, pressed && styles.pressed]}
              >
                <Text style={styles.serviceSymbol}>⌖</Text>
                <View style={styles.serviceCopy}>
                  <Text style={styles.serviceTitle}>장소 제보</Text>
                  <Text style={styles.serviceText}>새 장소와 수정 정보를 알려요</Text>
                </View>
                <Text style={styles.serviceArrow}>›</Text>
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
              <Pressable
                onPress={() =>
                  router.push({
                    pathname: "/explore",
                    params: {
                      q: "공원",
                      lat: nearbyCenter ? String(nearbyCenter.lat) : undefined,
                      lng: nearbyCenter ? String(nearbyCenter.lng) : undefined,
                    },
                  })
                }
              >
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
                        params: {
                          q: "공원",
                          placeId: String(place.id),
                          lat: nearbyCenter ? String(nearbyCenter.lat) : undefined,
                          lng: nearbyCenter ? String(nearbyCenter.lng) : undefined,
                        },
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
  screen: { flex: 1, backgroundColor: Palette.canvas },
  safeArea: { flex: 1 },
  content: {
    width: "100%",
    maxWidth: 760,
    alignSelf: "center",
    paddingHorizontal: Spacing.three,
    paddingTop: Spacing.three,
    paddingBottom: BottomTabInset + Spacing.six,
    gap: 30,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 9 },
  brandMark: { width: 34, height: 34, alignItems: "center", justifyContent: "center", borderRadius: 12, backgroundColor: Palette.accent },
  brandMarkText: { color: "#FFFFFF", fontSize: 20, fontWeight: "900" },
  brand: {
    color: Palette.ink,
    fontSize: 16,
    fontWeight: "900",
    letterSpacing: -0.4,
  },
  brandCaption: { marginTop: 1, color: Palette.muted, fontSize: 8, fontWeight: "800", letterSpacing: 1.8 },
  headerButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: Palette.border, borderRadius: 21, backgroundColor: Palette.surface },
  headerButtonText: { color: Palette.ink, fontSize: 24, fontWeight: "700" },
  hero: { paddingTop: Spacing.three },
  title: {
    color: "#17201D",
    fontSize: 34,
    lineHeight: 42,
    fontWeight: "900",
    letterSpacing: -1.3,
  },
  description: {
    maxWidth: 480,
    marginTop: 9,
    color: Palette.muted,
    fontSize: 14,
    lineHeight: 22,
  },
  searchBox: {
    marginTop: Spacing.three,
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
    minWidth: 92,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: Palette.accent,
  },
  searchButtonLabel: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  buttonDisabled: { opacity: 0.45 },
  placeSearchCard: {
    padding: 18,
    gap: 12,
    borderWidth: 1,
    borderColor: "#DCE5E1",
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  searchTitleRow: { flexDirection: "row", alignItems: "center", gap: 9 },
  searchIcon: { width: 32, height: 32, alignItems: "center", justifyContent: "center", borderRadius: 12, backgroundColor: Palette.accentSoft },
  searchIconText: { color: Palette.accent, fontSize: 20, fontWeight: "900" },
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
  categoryGrid: { marginTop: 14, flexDirection: "row", flexWrap: "wrap", gap: 9 },
  categoryCard: {
    width: "31%",
    flexGrow: 1,
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
  serviceGrid: { marginTop: 14, gap: 9 },
  serviceCard: { minHeight: 72, padding: 14, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1, borderColor: Palette.border, borderRadius: Radius.medium, backgroundColor: Palette.surface },
  serviceSymbol: { width: 32, color: Palette.accent, fontSize: 23, fontWeight: "900", textAlign: "center" },
  serviceCopy: { minWidth: 0, flex: 1 },
  serviceTitle: { color: Palette.ink, fontSize: 14, fontWeight: "900" },
  serviceText: { marginTop: 4, color: Palette.muted, fontSize: 11 },
  serviceArrow: { color: Palette.muted, fontSize: 24 },
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
