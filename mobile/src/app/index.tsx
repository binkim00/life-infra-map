import { searchLocation } from "@/utils/location";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { searchMapPlaces } from "@/api/recommendations";
import { BottomNav } from "@/components/bottom-nav";
import { AppIcon } from "@/components/app-icon";
import { PlacePhoto } from "@/components/place-photo";
import { BottomTabInset, Palette, Radius, Shadow } from "@/constants/theme";
import type { Place } from "@/types/place";

const CATEGORIES = [
  { label: "카페", query: "카페", ios: "cup.and.saucer.fill", android: "local_cafe" },
  { label: "식당", query: "식당", ios: "fork.knife", android: "restaurant" },
  { label: "주차", query: "무료 주차장", ios: "parkingsign.circle.fill", android: "local_parking" },
  { label: "화장실", query: "공중화장실", ios: "figure.dress.line.vertical.figure", android: "wc" },
  { label: "공원", query: "공원", ios: "tree.fill", android: "park" },
] as const;

const formatDistance = (distance?: number) => {
  if (!distance || distance <= 0) return "거리 확인 중";
  return distance < 1000 ? `${Math.round(distance)}m` : `${(distance / 1000).toFixed(1)}km`;
};

export default function HomeScreen() {
  const [placeQuery, setPlaceQuery] = useState("");
  const [nearbyPlaces, setNearbyPlaces] = useState<Place[]>([]);
  const [loading, setLoading] = useState(true);
  const [nearbyError, setNearbyError] = useState("");
  const [nearbyReloadKey, setNearbyReloadKey] = useState(0);
  const [nearbyCenter, setNearbyCenter] = useState<{ lat: number; lng: number } | null>(null);

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
      const coordinates = await searchLocation({ cachedOnly: true });
      if (!coordinates) throw new Error("위치 버튼을 누르면 주변 장소를 볼 수 있어요.");
      const nextCenter = { lat: coordinates.latitude, lng: coordinates.longitude };
      if (active) setNearbyCenter(nextCenter);
      return searchMapPlaces({ query: "공원", lat: nextCenter.lat, lng: nextCenter.lng, limit: 6, signal: controller.signal });
    };
    loadNearbyParks()
      .then((data) => {
        if (!active) return;
        setNearbyPlaces(data.results);
        setNearbyError(data.message || "");
      })
      .catch((error) => {
        if (!active || error?.name === "AbortError") return;
        setNearbyPlaces([]);
        setNearbyError(error instanceof Error ? error.message : "주변 장소를 불러오지 못했습니다.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [nearbyReloadKey]);

  const openNearby = (place?: Place) => router.push({
    pathname: "/explore",
    params: {
      q: "공원",
      placeId: place ? String(place.id) : undefined,
      lat: nearbyCenter ? String(nearbyCenter.lat) : undefined,
      lng: nearbyCenter ? String(nearbyCenter.lng) : undefined,
    },
  });

  return (
    <View style={styles.screen}>
      <SafeAreaView style={styles.safeArea} edges={["top", "left", "right"]}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <View style={styles.brandRow}>
              <View style={styles.pinLogo}><View style={styles.pinDot} /></View>
              <View><Text style={styles.brand}>여기일지도</Text><Text style={styles.brandCaption}>LIFE MAP</Text></View>
            </View>
            <Pressable accessibilityLabel="알림 보기" onPress={() => router.push("/notifications")} style={styles.iconButton}>
              <AppIcon ios="bell.fill" android="notifications" size={25} color={Palette.ink} /><View style={styles.alertDot} />
            </Pressable>
          </View>

          <View style={styles.hero}>
            <Text style={styles.title}>오늘 어디로 갈까요?</Text>
            <Text style={styles.description}>좋은 장소가, 좋은 하루를 만들어요.</Text>
          </View>

          <View style={styles.modeStack}>
            <Pressable onPress={() => router.push("/recommend")} style={({ pressed }) => [styles.modeCard, pressed && styles.pressed]}>
              <View style={[styles.modeIcon, styles.modeIconCoral]}><AppIcon ios="sparkles" android="auto_awesome" size={26} color={Palette.coral} /></View>
              <View style={styles.modeCopy}><Text style={styles.modeTitle}>상황으로 찾기</Text><Text style={styles.modeDescription}>지금 상황에 맞는 장소를 추천해요</Text></View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
            <View style={styles.searchCard}>
              <View style={styles.searchTop}>
                <View style={[styles.modeIcon, styles.modeIconMint]}><AppIcon ios="magnifyingglass" android="search" size={26} color={Palette.accent} /></View>
                <View style={styles.modeCopy}><Text style={styles.modeTitle}>일반 장소 검색</Text><Text style={styles.modeDescription}>장소명이나 지역·업종을 빠르게 찾아요</Text></View>
              </View>
              <View style={styles.searchRow}>
                <TextInput value={placeQuery} onChangeText={setPlaceQuery} onSubmitEditing={() => openPlaceSearch()} placeholder="예: 서면역 약국, 광안리 주차장" placeholderTextColor="#7A8580" returnKeyType="search" style={styles.searchInput} />
                <Pressable onPress={() => openPlaceSearch()} style={styles.searchButton}><Text style={styles.searchButtonText}>검색</Text></Pressable>
              </View>
            </View>
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categoryRow}>
            {CATEGORIES.map((item) => (
              <Pressable key={item.label} onPress={() => openPlaceSearch(item.query)} style={({ pressed }) => [styles.category, pressed && styles.pressed]}>
                <View style={styles.categoryIcon}><AppIcon ios={item.ios} android={item.android} size={20} color={Palette.accent} /></View><Text style={styles.categoryLabel}>{item.label}</Text>
              </Pressable>
            ))}
          </ScrollView>

          <View style={styles.sectionHeader}>
            <View><Text style={styles.sectionTitle}>지금, 주변에 이런 곳은 어때요?</Text><Text style={styles.sectionCaption}>가까운 장소를 한눈에 둘러보세요.</Text></View>
            <Pressable onPress={() => openNearby()}><Text style={styles.more}>더보기  ›</Text></Pressable>
          </View>

          {loading ? (
            <View style={styles.stateCard}><ActivityIndicator color={Palette.accent} /><Text style={styles.stateText}>주변 장소를 찾고 있어요</Text></View>
          ) : nearbyPlaces.length ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.placesRow}>
              {nearbyPlaces.slice(0, 5).map((place, index) => (
                <Pressable key={place.id} onPress={() => openNearby(place)} style={({ pressed }) => [styles.placeCard, pressed && styles.pressed]}>
                  <PlacePhoto category={index % 2 ? "walk" : place.category || "park"} fallback={index} width={164} height={106} style={styles.placeVisual}>
                    <View style={styles.distanceBadge}><Text style={styles.distanceBadgeText}>⌖ {formatDistance(place.distance)}</Text></View>
                  </PlacePhoto>
                  <Text numberOfLines={1} style={styles.placeName}>{place.name}</Text>
                  <Text numberOfLines={1} style={styles.placeMeta}>{place.category_label || "공원 · 산책하기 좋아요"}</Text>
                  <View style={styles.placeFoot}><Text style={styles.star}>★</Text><Text style={styles.placeSource}>{place.source_label || "여기일지도"}</Text></View>
                </Pressable>
              ))}
            </ScrollView>
          ) : (
            <View style={styles.stateCard}>
              <Text style={styles.stateTitle}>주변 장소를 아직 보여드릴 수 없어요</Text><Text style={styles.stateText}>{nearbyError || "위치 확인 후 다시 시도해 주세요."}</Text>
              <Pressable onPress={() => { setLoading(true); setNearbyError(""); setNearbyReloadKey((value) => value + 1); }} style={styles.retryButton}><Text style={styles.retryText}>다시 시도</Text></Pressable>
            </View>
          )}

          <Pressable onPress={() => router.push("/place-report")} style={({ pressed }) => [styles.discoveryBanner, pressed && styles.pressed]}>
            <View style={styles.bannerCopy}><Text style={styles.bannerTitle}>지도의 작은 발견이{`\n`}오늘을 더 특별하게</Text><Text style={styles.bannerText}>빠진 장소와 정보를 알려주세요.</Text></View>
            <View style={styles.miniMap}><View style={styles.mapRoadA} /><View style={styles.mapRoadB} /><View style={styles.mapPin}><Text style={styles.mapPinText}>●</Text></View></View>
          </Pressable>

          <View style={styles.communityRow}>
            <Pressable onPress={() => router.push("/boards/free")} style={styles.communityButton}><AppIcon ios="bubble.left.and.bubble.right.fill" android="forum" size={19} color={Palette.accent} /><Text style={styles.communityText}>커뮤니티</Text><Text style={styles.communityArrow}>›</Text></Pressable>
            <Pressable onPress={() => router.push("/place-report")} style={styles.communityButton}><AppIcon ios="mappin.and.ellipse" android="add_location_alt" size={20} color={Palette.accent} /><Text style={styles.communityText}>장소 제보</Text><Text style={styles.communityArrow}>›</Text></Pressable>
          </View>
        </ScrollView>
      </SafeAreaView>
      <BottomNav />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Palette.canvas }, safeArea: { flex: 1 },
  content: { paddingHorizontal: 20, paddingTop: 10, paddingBottom: BottomTabInset + 26, gap: 20 },
  header: { height: 54, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, brandRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  pinLogo: { width: 34, height: 39, alignItems: "center", paddingTop: 8, borderTopLeftRadius: 18, borderTopRightRadius: 18, borderBottomLeftRadius: 18, backgroundColor: Palette.accent, transform: [{ rotate: "45deg" }] }, pinDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: "#FFFFFF" },
  brand: { color: Palette.ink, fontSize: 20, fontWeight: "900", letterSpacing: -0.7 }, brandCaption: { marginTop: 1, color: Palette.ink, fontSize: 8, fontWeight: "800", letterSpacing: 2.2 },
  iconButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center", position: "relative" }, alertDot: { position: "absolute", right: 8, top: 7, width: 7, height: 7, borderRadius: 4, backgroundColor: Palette.coral },
  hero: { paddingTop: 11 }, title: { color: Palette.ink, fontSize: 31, lineHeight: 38, fontWeight: "900", letterSpacing: -1.2 }, description: { marginTop: 5, color: Palette.muted, fontSize: 14, lineHeight: 21 },
  modeStack: { gap: 10 }, modeCard: { minHeight: 82, padding: 15, flexDirection: "row", alignItems: "center", gap: 13, borderWidth: 1, borderColor: Palette.border, borderRadius: Radius.medium, backgroundColor: Palette.surface, boxShadow: Shadow.card },
  modeIcon: { width: 48, height: 48, alignItems: "center", justifyContent: "center", borderRadius: 17 }, modeIconCoral: { backgroundColor: Palette.coralSoft }, modeIconMint: { backgroundColor: Palette.accentSoft },
  modeCopy: { minWidth: 0, flex: 1 }, modeTitle: { color: Palette.ink, fontSize: 16, fontWeight: "900" }, modeDescription: { marginTop: 5, color: Palette.muted, fontSize: 11.5 }, chevron: { color: Palette.ink, fontSize: 27, fontWeight: "300" },
  searchCard: { padding: 15, gap: 13, borderWidth: 1, borderColor: Palette.border, borderRadius: Radius.medium, backgroundColor: Palette.surface, boxShadow: Shadow.card }, searchTop: { flexDirection: "row", alignItems: "center", gap: 13 }, searchRow: { flexDirection: "row", gap: 8 },
  searchInput: { minWidth: 0, height: 45, flex: 1, paddingHorizontal: 13, borderWidth: 1, borderColor: "#CFDAD5", borderRadius: 12, color: Palette.ink, fontSize: 12.5 }, searchButton: { width: 72, height: 45, alignItems: "center", justifyContent: "center", borderRadius: 12, backgroundColor: Palette.accent }, searchButtonText: { color: "#FFFFFF", fontSize: 13, fontWeight: "900" },
  categoryRow: { gap: 8, paddingRight: 8 }, category: { width: 68, paddingVertical: 10, alignItems: "center", gap: 7, borderRadius: 15, backgroundColor: Palette.surfaceMuted }, categoryIcon: { height: 25, alignItems: "center", justifyContent: "center" }, categoryLabel: { color: Palette.ink, fontSize: 11, fontWeight: "800" },
  sectionHeader: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: 8 }, sectionTitle: { color: Palette.ink, fontSize: 17, fontWeight: "900", letterSpacing: -0.4 }, sectionCaption: { marginTop: 4, color: Palette.muted, fontSize: 11 }, more: { color: Palette.ink, fontSize: 11, fontWeight: "800" },
  placesRow: { gap: 10, paddingRight: 10 }, placeCard: { width: 164, paddingBottom: 11, overflow: "hidden", borderWidth: 1, borderColor: Palette.border, borderRadius: 15, backgroundColor: Palette.surface }, placeVisual: { position: "relative" },
  distanceBadge: { position: "absolute", left: 8, bottom: 7, paddingHorizontal: 7, paddingVertical: 4, borderRadius: 8, backgroundColor: "rgba(23,32,29,0.76)" }, distanceBadgeText: { color: "#FFFFFF", fontSize: 9, fontWeight: "800" }, placeName: { marginTop: 10, paddingHorizontal: 10, color: Palette.ink, fontSize: 13, fontWeight: "900" }, placeMeta: { marginTop: 4, paddingHorizontal: 10, color: Palette.muted, fontSize: 9.5 }, placeFoot: { marginTop: 7, paddingHorizontal: 10, flexDirection: "row", alignItems: "center", gap: 5 }, star: { color: "#FFAA2A", fontSize: 11 }, placeSource: { color: Palette.accent, fontSize: 9.5, fontWeight: "700" },
  stateCard: { minHeight: 112, padding: 18, alignItems: "center", justifyContent: "center", gap: 7, borderRadius: Radius.medium, backgroundColor: Palette.surfaceMuted }, stateTitle: { color: Palette.ink, fontSize: 13, fontWeight: "900", textAlign: "center" }, stateText: { color: Palette.muted, fontSize: 11, lineHeight: 17, textAlign: "center" }, retryButton: { marginTop: 4, paddingHorizontal: 13, paddingVertical: 8, borderRadius: 10, backgroundColor: Palette.accent }, retryText: { color: "#FFFFFF", fontSize: 11, fontWeight: "800" },
  discoveryBanner: { minHeight: 132, padding: 18, flexDirection: "row", alignItems: "center", overflow: "hidden", borderRadius: Radius.medium, backgroundColor: "#DDF3EE" }, bannerCopy: { zIndex: 2, flex: 1 }, bannerTitle: { color: "#164B45", fontSize: 17, lineHeight: 24, fontWeight: "900" }, bannerText: { marginTop: 6, color: "#4D716B", fontSize: 10.5 },
  miniMap: { width: 122, height: 92, position: "relative", overflow: "hidden", borderRadius: 15, backgroundColor: "rgba(255,255,255,0.74)", transform: [{ rotate: "-5deg" }] }, mapRoadA: { position: "absolute", left: -10, top: 37, width: 150, height: 13, backgroundColor: "#F4D9C7", transform: [{ rotate: "22deg" }] }, mapRoadB: { position: "absolute", left: 53, top: -10, width: 14, height: 120, backgroundColor: "#FFFFFF", transform: [{ rotate: "-18deg" }] }, mapPin: { position: "absolute", left: 50, top: 25, width: 29, height: 34, alignItems: "center", justifyContent: "center", borderTopLeftRadius: 15, borderTopRightRadius: 15, borderBottomLeftRadius: 15, backgroundColor: Palette.coral, transform: [{ rotate: "45deg" }] }, mapPinText: { color: "#FFFFFF", fontSize: 8 },
  communityRow: { flexDirection: "row", gap: 10 }, communityButton: { minHeight: 58, paddingHorizontal: 13, flex: 1, flexDirection: "row", alignItems: "center", gap: 8, borderWidth: 1, borderColor: Palette.border, borderRadius: 15, backgroundColor: Palette.surface }, communityText: { minWidth: 0, flex: 1, color: Palette.ink, fontSize: 12.5, fontWeight: "900" }, communityArrow: { color: Palette.muted, fontSize: 20 }, pressed: { opacity: 0.65, transform: [{ scale: 0.985 }] },
});
