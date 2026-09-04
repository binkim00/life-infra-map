import { useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";

import { Palette, Radius, Shadow, Spacing } from "@/constants/theme";
import type { Place } from "@/types/place";

const formatDistance = (distance?: number) => {
  if (distance === undefined || distance === null) return "거리 정보 없음";
  return distance < 1000
    ? `${Math.round(distance)}m`
    : `${(distance / 1000).toFixed(1)}km`;
};

const kakaoMapUrl = (place: Place) =>
  place.kakao_place_url ||
  `https://map.kakao.com/link/map/${encodeURIComponent(place.name)},${place.lat},${place.lng}`;

const kakaoDetailUrl = (place: Place) => {
  const url = place.place_url || place.kakao_place_url || "";
  if (!url) return "";
  return url.replace(/^http:\/\//i, "https://");
};

export function PlaceDetailSheet({
  place,
  visible,
  onClose,
  onSave,
  onReport,
}: {
  place: Place | null;
  visible: boolean;
  onClose: () => void;
  onSave: () => void;
  onReport: () => void;
}) {
  const [showWebDetail, setShowWebDetail] = useState(false);
  const [webDetailError, setWebDetailError] = useState(false);

  if (!place) return null;

  const detailUrl = kakaoDetailUrl(place);
  const tags = place.tags?.slice(0, 8) || [];
  const smoking = place.smoking;

  return (
    <Modal
      animationType="slide"
      transparent
      visible={visible}
      onRequestClose={onClose}
    >
      <View style={styles.backdrop}>
        <Pressable accessibilityLabel="장소 상세 닫기" onPress={onClose} style={StyleSheet.absoluteFill} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
            <View style={styles.headingRow}>
              <View style={styles.headingCopy}>
                <Text style={styles.eyebrow}>{place.category_label || place.category || "장소"}</Text>
                <Text style={styles.name}>{place.name}</Text>
              </View>
              <Pressable accessibilityRole="button" onPress={onClose} style={styles.closeButton}>
                <Text style={styles.closeText}>닫기</Text>
              </Pressable>
            </View>

            <View style={styles.infoCard}>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>거리</Text>
                <Text style={styles.infoValue}>{formatDistance(place.distance)}</Text>
              </View>
              <View style={styles.divider} />
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>주소</Text>
                <Text style={styles.infoValue}>{place.address || place.detail_location || "주소 정보 없음"}</Text>
              </View>
              {place.phone ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>전화</Text>
                    <Pressable onPress={() => Linking.openURL(`tel:${place.phone}`)}>
                      <Text style={[styles.infoValue, styles.link]}>{place.phone}</Text>
                    </Pressable>
                  </View>
                </>
              ) : null}
              <View style={styles.divider} />
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>정보 출처</Text>
                <Text style={styles.infoValue}>{place.source_label || place.source_name || "LifeMap 장소 데이터"}</Text>
              </View>
              {smoking?.facility_type ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>시설 유형</Text>
                    <Text style={styles.infoValue}>{smoking.facility_type_label || smoking.facility_type}</Text>
                  </View>
                </>
              ) : null}
              {smoking?.verification_level ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>확인 수준</Text>
                    <Text style={styles.infoValue}>{smoking.verification_level_label || smoking.verification_level}</Text>
                  </View>
                </>
              ) : null}
              {smoking?.location_description ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>시설 위치</Text>
                    <Text style={styles.infoValue}>{smoking.location_description}</Text>
                  </View>
                </>
              ) : null}
              {smoking?.location_directions ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>찾아가는 법</Text>
                    <Text style={styles.infoValue}>{smoking.location_directions}</Text>
                  </View>
                </>
              ) : null}
            </View>

            {tags.length ? (
              <View>
                <Text style={styles.sectionTitle}>장소 특징</Text>
                <View style={styles.tags}>
                  {tags.map((tag) => (
                    <Text key={`${place.id}-${tag.id ?? tag.name}`} style={styles.tag}>#{tag.name}</Text>
                  ))}
                </View>
              </View>
            ) : (
              <Text style={styles.notice}>아직 등록된 상세 특징이 적습니다. 카카오 장소 정보에서 영업시간과 최신 정보를 확인해 주세요.</Text>
            )}

            <View style={styles.primaryActions}>
              {detailUrl ? (
                <Pressable
                  onPress={() => {
                    setWebDetailError(false);
                    setShowWebDetail(true);
                  }}
                  style={styles.primaryButton}
                >
                  <Text style={styles.primaryButtonText}>사진 · 리뷰 · 상세정보 보기</Text>
                  <Text style={styles.primaryButtonCaption}>카카오 장소 정보가 앱 안에서 열립니다</Text>
                </Pressable>
              ) : null}
              <Pressable onPress={() => Linking.openURL(kakaoMapUrl(place))} style={styles.secondaryButton}>
                <Text style={styles.secondaryButtonText}>카카오맵에서 위치 · 길찾기</Text>
              </Pressable>
            </View>

            <View style={styles.utilityActions}>
              <Pressable onPress={onSave} style={styles.utilityButton}>
                <Text style={styles.utilityText}>저장</Text>
              </Pressable>
              <Pressable onPress={onReport} style={styles.utilityButton}>
                <Text style={styles.utilityText}>정보 수정 제보</Text>
              </Pressable>
            </View>
          </ScrollView>
        </View>
      </View>
      <Modal
        animationType="slide"
        onRequestClose={() => setShowWebDetail(false)}
        visible={showWebDetail}
      >
        <SafeAreaView style={styles.webDetailScreen} edges={["top", "bottom", "left", "right"]}>
          <View style={styles.webDetailHeader}>
            <View style={styles.webDetailHeading}>
              <Text numberOfLines={1} style={styles.webDetailTitle}>{place.name}</Text>
              <Text style={styles.webDetailCaption}>카카오 제공 사진 · 리뷰 · 영업정보</Text>
            </View>
            <Pressable onPress={() => setShowWebDetail(false)} style={styles.closeButton}>
              <Text style={styles.closeText}>닫기</Text>
            </Pressable>
          </View>
          {webDetailError ? (
            <View style={styles.webDetailFallback}>
              <Text style={styles.webDetailFallbackTitle}>상세정보를 앱 안에서 열지 못했습니다.</Text>
              <Text style={styles.webDetailFallbackText}>카카오맵에서 사진과 최신 정보를 확인해 주세요.</Text>
              <Pressable onPress={() => Linking.openURL(detailUrl)} style={styles.primaryButton}>
                <Text style={styles.primaryButtonText}>카카오맵에서 열기</Text>
              </Pressable>
            </View>
          ) : detailUrl ? (
            <WebView
              source={{ uri: detailUrl }}
              style={styles.webDetail}
              javaScriptEnabled
              domStorageEnabled
              startInLoadingState
              onError={() => setWebDetailError(true)}
              renderLoading={() => (
                <View style={styles.webDetailLoading}>
                  <ActivityIndicator color={Palette.accent} />
                  <Text style={styles.webDetailFallbackText}>장소 정보를 불러오는 중입니다.</Text>
                </View>
              )}
            />
          ) : null}
        </SafeAreaView>
      </Modal>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(14, 24, 21, 0.42)" },
  sheet: {
    maxHeight: "82%",
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: "#F8FAF9",
    boxShadow: Shadow.card,
  },
  handle: { width: 42, height: 4, marginTop: 10, alignSelf: "center", borderRadius: 2, backgroundColor: "#CBD5D1" },
  content: { padding: Spacing.four, paddingBottom: 34, gap: Spacing.four },
  headingRow: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  headingCopy: { minWidth: 0, flex: 1 },
  eyebrow: { color: Palette.accent, fontSize: 12, fontWeight: "800" },
  name: { marginTop: 6, color: Palette.ink, fontSize: 25, fontWeight: "900", letterSpacing: -0.5 },
  closeButton: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: Radius.pill, backgroundColor: "#E9EFEC" },
  closeText: { color: Palette.muted, fontSize: 12, fontWeight: "800" },
  infoCard: { padding: 16, borderWidth: 1, borderColor: "#E1E8E4", borderRadius: Radius.medium, backgroundColor: Palette.surface },
  infoRow: { flexDirection: "row", alignItems: "flex-start", gap: 14 },
  infoLabel: { width: 58, color: Palette.muted, fontSize: 12, fontWeight: "700" },
  infoValue: { minWidth: 0, flex: 1, color: Palette.ink, fontSize: 13, fontWeight: "700", lineHeight: 19 },
  link: { color: Palette.accent },
  divider: { height: 1, marginVertical: 12, backgroundColor: "#EDF1EF" },
  sectionTitle: { marginBottom: 10, color: Palette.ink, fontSize: 14, fontWeight: "900" },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  tag: { paddingHorizontal: 10, paddingVertical: 7, overflow: "hidden", borderRadius: Radius.pill, backgroundColor: "#E4F2EE", color: Palette.accent, fontSize: 11, fontWeight: "800" },
  notice: { padding: 14, borderRadius: Radius.small, backgroundColor: "#F0F3F1", color: Palette.muted, fontSize: 12, lineHeight: 18 },
  primaryActions: { gap: 8 },
  primaryButton: { minHeight: 52, alignItems: "center", justifyContent: "center", borderRadius: Radius.medium, backgroundColor: Palette.accent },
  primaryButtonText: { color: "#FFFFFF", fontSize: 14, fontWeight: "900" },
  primaryButtonCaption: { marginTop: 3, color: "#D7F0EB", fontSize: 10, fontWeight: "700" },
  secondaryButton: { minHeight: 48, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#C9D8D3", borderRadius: Radius.medium, backgroundColor: Palette.surface },
  secondaryButtonText: { color: Palette.accent, fontSize: 13, fontWeight: "800" },
  utilityActions: { flexDirection: "row", gap: 8 },
  utilityButton: { flex: 1, minHeight: 44, alignItems: "center", justifyContent: "center" },
  utilityText: { color: Palette.muted, fontSize: 12, fontWeight: "800", textDecorationLine: "underline" },
  webDetailScreen: { flex: 1, backgroundColor: Palette.surface },
  webDetailHeader: { minHeight: 68, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: "#E1E8E4" },
  webDetailHeading: { minWidth: 0, flex: 1 },
  webDetailTitle: { color: Palette.ink, fontSize: 17, fontWeight: "900" },
  webDetailCaption: { marginTop: 3, color: Palette.muted, fontSize: 10, fontWeight: "700" },
  webDetail: { flex: 1, backgroundColor: "#FFFFFF" },
  webDetailLoading: { position: "absolute", inset: 0, alignItems: "center", justifyContent: "center", gap: 10, backgroundColor: "#FFFFFF" },
  webDetailFallback: { flex: 1, alignItems: "stretch", justifyContent: "center", padding: 24, gap: 12 },
  webDetailFallbackTitle: { color: Palette.ink, fontSize: 17, fontWeight: "900", textAlign: "center" },
  webDetailFallbackText: { color: Palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" },
});
