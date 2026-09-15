import { type ComponentProps, useRef, useState } from "react";
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
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";

import { Palette, Radius, Shadow, Spacing } from "@/constants/theme";
import type { Place } from "@/types/place";

const WEB_CONTENT_HEIGHT_SCRIPT = `
  (function () {
    function reportHeight() {
      var body = document.body;
      var root = document.documentElement;
      var height = Math.max(
        body ? body.scrollHeight : 0,
        body ? body.offsetHeight : 0,
        root ? root.scrollHeight : 0,
        root ? root.offsetHeight : 0
      );
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'contentHeight', height: height }));
    }
    window.addEventListener('load', reportHeight);
    window.addEventListener('resize', reportHeight);
    if (window.ResizeObserver && document.documentElement) {
      new ResizeObserver(reportHeight).observe(document.documentElement);
    }
    setTimeout(reportHeight, 100);
    setTimeout(reportHeight, 500);
    setTimeout(reportHeight, 1500);
  })();
  true;
`;

const formatDistance = (distance?: number) => {
  if (distance === undefined || distance === null || distance <= 0)
    return "거리 정보 없음";
  return distance < 1000
    ? `${Math.round(distance)}m`
    : `${(distance / 1000).toFixed(1)}km`;
};

const CATEGORY_LABELS: Record<string, string> = {
  cafe: "카페",
  restaurant: "음식점",
  city_park: "공원",
  parking: "주차장",
  toilet: "화장실",
  smoking_area: "흡연구역",
  library: "도서관",
  hospital: "병원",
  pharmacy: "약국",
  convenience_store: "편의점",
};

const categoryLabel = (place: Place) =>
  place.category_label ||
  CATEGORY_LABELS[place.category] ||
  place.category ||
  "장소";

const kakaoMapUrl = (place: Place) =>
  place.kakao_place_url ||
  `https://map.kakao.com/link/map/${encodeURIComponent(place.name)},${place.lat},${place.lng}`;

const hasMapCoordinates = (place: Place) =>
  place.lat !== null &&
  place.lat !== undefined &&
  place.lng !== null &&
  place.lng !== undefined &&
  Number.isFinite(Number(place.lat)) &&
  Number.isFinite(Number(place.lng));

const kakaoDetailUrl = (place: Place) => {
  const url = place.place_url || place.kakao_place_url || "";
  if (url) return url.replace(/^http:\/\//i, "https://");
  if (place.kakao_place_id && /^\d{5,20}$/.test(place.kakao_place_id)) {
    return `https://place.map.kakao.com/${place.kakao_place_id}`;
  }
  return "";
};

const isKakaoPlace = (place: Place) => {
  const detailUrl = `${place.place_url || ""} ${place.kakao_place_url || ""}`.toLowerCase();
  const source =
    `${place.result_source || ""} ${place.source_label || ""} ${place.source_name || ""}`.toLowerCase();
  return (
    Boolean(place.kakao_place_url) ||
    detailUrl.includes("place.map.kakao.com") ||
    detailUrl.includes("map.kakao.com") ||
    source.includes("kakao") ||
    source.includes("카카오")
  );
};

export function PlaceDetailSheet(
  props: ComponentProps<typeof PlaceDetailContent>,
) {
  if (!props.visible || !props.place) return null;
  return <PlaceDetailContent key={props.place.id} {...props} />;
}

function PlaceDetailContent({
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
  const [showWebDetail, setShowWebDetail] = useState(() => Boolean(place && kakaoDetailUrl(place) && isKakaoPlace(place)));
  const [webDetailError, setWebDetailError] = useState(false);
  const [externalError, setExternalError] = useState("");
  const webViewRef = useRef<WebView>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [webContentHeight, setWebContentHeight] = useState(720);
  const [webReloadKey, setWebReloadKey] = useState(0);
  const insets = useSafeAreaInsets();

  if (!place) return null;

  const detailUrl = kakaoDetailUrl(place);
  const kakaoSource = isKakaoPlace(place);
  const detailSourceName = kakaoSource ? "카카오 장소 정보" : "원문 상세정보";
  const tags = place.tags?.slice(0, 8) || [];
  const smoking = place.smoking;
  const openExternal = async (url: string) => {
    setExternalError("");
    try {
      const supported = await Linking.canOpenURL(url);
      if (!supported) throw new Error("unsupported");
      await Linking.openURL(url);
    } catch {
      setExternalError("연결된 앱을 열지 못했습니다. 잠시 후 다시 시도해 주세요.");
    }
  };

  const embedded = Boolean(showWebDetail && detailUrl);
  const goBack = () => {
    if (embedded && canGoBack && !webDetailError) webViewRef.current?.goBack();
    else onClose();
  };

  return (
    <Modal
      animationType="slide"
      transparent
      visible={visible}
      onRequestClose={goBack}
    >
      <View style={styles.backdrop}>
        <Pressable
          accessibilityLabel="장소 상세 닫기"
          onPress={onClose}
          style={StyleSheet.absoluteFill}
        />
        <View style={[styles.sheet, embedded && styles.embeddedSheet, { paddingBottom: insets.bottom }]}>
          <View style={styles.handle} />
            <View style={[styles.headingRow, styles.fixedHeading]}>
              <View style={styles.headingCopy}>
                <Text style={styles.eyebrow}>{categoryLabel(place)}</Text>
                <Text style={styles.name}>{place.name}</Text>
              </View>
              <Pressable
                accessibilityRole="button"
                onPress={onClose}
                style={styles.closeButton}
              >
                <Text style={styles.closeText}>닫기</Text>
              </Pressable>
            </View>
          <ScrollView
            contentContainerStyle={styles.content}
            showsVerticalScrollIndicator={false}
            nestedScrollEnabled
          >
            <View style={styles.infoCard}>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>거리</Text>
                <Text style={styles.infoValue}>
                  {formatDistance(place.distance)}
                </Text>
              </View>
              <View style={styles.divider} />
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>주소</Text>
                <Text style={styles.infoValue}>
                  {place.address || place.detail_location || "주소 정보 없음"}
                </Text>
              </View>
              {place.phone ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>전화</Text>
                    <Pressable
                      onPress={() => void openExternal(`tel:${place.phone}`)}
                    >
                      <Text style={[styles.infoValue, styles.link]}>
                        {place.phone}
                      </Text>
                    </Pressable>
                  </View>
                </>
              ) : null}
              <View style={styles.divider} />
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>정보 출처</Text>
                <Text style={styles.infoValue}>
                  {place.source_label ||
                    place.source_name ||
                    "LifeMap 장소 데이터"}
                </Text>
              </View>
              {smoking?.facility_type ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>시설 유형</Text>
                    <Text style={styles.infoValue}>
                      {smoking.facility_type_label || smoking.facility_type}
                    </Text>
                  </View>
                </>
              ) : null}
              {smoking?.verification_level ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>확인 수준</Text>
                    <Text style={styles.infoValue}>
                      {smoking.verification_level_label ||
                        smoking.verification_level}
                    </Text>
                  </View>
                </>
              ) : null}
              {smoking?.location_description ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>시설 위치</Text>
                    <Text style={styles.infoValue}>
                      {smoking.location_description}
                    </Text>
                  </View>
                </>
              ) : null}
              {smoking?.location_directions ? (
                <>
                  <View style={styles.divider} />
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>찾아가는 법</Text>
                    <Text style={styles.infoValue}>
                      {smoking.location_directions}
                    </Text>
                  </View>
                </>
              ) : null}
            </View>

            {tags.length ? (
              <View>
                <Text style={styles.sectionTitle}>장소 특징</Text>
                <View style={styles.tags}>
                  {tags.map((tag) => (
                    <Text
                      key={`${place.id}-${tag.id ?? tag.name}`}
                      style={styles.tag}
                    >
                      #{tag.name}
                      {tag.is_verified ? " · 확인됨" : " · 확인 필요"}
                    </Text>
                  ))}
                </View>
              </View>
            ) : (
              <Text style={styles.notice}>
                {detailUrl
                  ? `아직 등록된 상세 특징이 적습니다. ${detailSourceName}에서 영업시간과 최신 정보를 확인해 주세요.`
                  : "사진·영업시간을 확인할 외부 장소 링크가 없습니다. 확인되지 않은 정보는 표시하지 않습니다."}
              </Text>
            )}

            <View style={styles.primaryActions}>
              {detailUrl && !embedded ? (
                <Pressable
                  onPress={() => {
                    setWebDetailError(false);
                    setShowWebDetail(true);
                  }}
                  style={styles.primaryButton}
                >
                  <Text style={styles.primaryButtonText}>
                    사진 · 리뷰 · 상세정보 보기
                  </Text>
                  <Text style={styles.primaryButtonCaption}>
                    {detailSourceName}가 앱 안에서 열립니다
                  </Text>
                </Pressable>
              ) : null}
              {place.kakao_place_url || hasMapCoordinates(place) ? (
                <Pressable
                  onPress={() => void openExternal(kakaoMapUrl(place))}
                  style={styles.secondaryButton}
                >
                  <Text style={styles.secondaryButtonText}>
                    카카오맵에서 위치 · 길찾기
                  </Text>
                </Pressable>
              ) : null}
            </View>

            {embedded ? (
            <View style={styles.embeddedSection}>
              <View style={styles.webDetailHeader}>
                <Text style={styles.webDetailTitle}>{detailSourceName}</Text>
                {canGoBack && !webDetailError ? (
                  <Pressable accessibilityRole="button" onPress={() => webViewRef.current?.goBack()} style={styles.closeButton}>
                    <Text style={styles.closeText}>웹페이지 뒤로</Text>
                  </Pressable>
                ) : null}
              </View>
              {webDetailError ? (
                <View style={styles.webDetailFallback}>
                  <Text style={styles.webDetailFallbackTitle}>장소 정보를 불러오지 못했습니다.</Text>
                  <Pressable accessibilityRole="button" onPress={() => { setCanGoBack(false); setWebDetailError(false); setWebContentHeight(720); setWebReloadKey((value) => value + 1); }} style={styles.primaryButton}>
                    <Text style={styles.primaryButtonText}>다시 시도</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" onPress={() => void openExternal(detailUrl)} style={styles.secondaryButton}>
                    <Text style={styles.secondaryButtonText}>외부에서 열기</Text>
                  </Pressable>
                </View>
              ) : (
                <WebView
                  key={webReloadKey}
                  ref={webViewRef}
                  source={{ uri: detailUrl }}
                  style={[styles.webDetail, { height: webContentHeight }]}
                  javaScriptEnabled
                  domStorageEnabled
                  startInLoadingState
                  scrollEnabled={false}
                  nestedScrollEnabled={false}
                  injectedJavaScript={WEB_CONTENT_HEIGHT_SCRIPT}
                  onLoadEnd={() => webViewRef.current?.injectJavaScript(WEB_CONTENT_HEIGHT_SCRIPT)}
                  onMessage={(event) => {
                    try {
                      const message = JSON.parse(event.nativeEvent.data);
                      if (message.type !== "contentHeight") return;
                      const height = Number(message.height);
                      if (Number.isFinite(height) && height > 0)
                        setWebContentHeight(Math.min(Math.max(Math.ceil(height), 560), 12000));
                    } catch {
                      // Ignore messages not emitted by the height bridge.
                    }
                  }}
                  onNavigationStateChange={(state) => setCanGoBack(state.canGoBack)}
                  onShouldStartLoadWithRequest={(request) => {
                    if (/^https?:\/\//i.test(request.url) || request.url === "about:blank") return true;
                    void openExternal(request.url);
                    return false;
                  }}
                  onError={() => setWebDetailError(true)}
                  onHttpError={(event) => { if (event.nativeEvent.url === detailUrl) setWebDetailError(true); }}
                  renderLoading={() => <View style={styles.webDetailLoading}><ActivityIndicator color={Palette.accent} /><Text style={styles.webDetailFallbackText}>장소 정보를 불러오는 중입니다.</Text></View>}
                />
              )}
            </View>
          ) : null}
            {externalError ? <Text style={styles.externalError}>{externalError}</Text> : null}
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
    </Modal>
  );
}

const styles = StyleSheet.create({
  embeddedSheet: { height: "90%", maxHeight: "90%" },
  fixedHeading: { paddingHorizontal: 16, paddingVertical: 12 },
  embeddedSection: { minHeight: 120, overflow: "hidden", borderRadius: 16, borderWidth: 1, borderColor: "#E1E8E4", backgroundColor: "#FFFFFF" },
  backdrop: {
    flex: 1,
    justifyContent: "flex-end",
    backgroundColor: "rgba(14, 24, 21, 0.42)",
  },
  sheet: {
    maxHeight: "82%",
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: "#F8FAF9",
    boxShadow: Shadow.card,
  },
  handle: {
    width: 42,
    height: 4,
    marginTop: 10,
    alignSelf: "center",
    borderRadius: 2,
    backgroundColor: "#CBD5D1",
  },
  content: { padding: Spacing.four, paddingBottom: 34, gap: Spacing.four },
  headingRow: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  headingCopy: { minWidth: 0, flex: 1 },
  eyebrow: { color: Palette.accent, fontSize: 12, fontWeight: "800" },
  name: {
    marginTop: 6,
    color: Palette.ink,
    fontSize: 25,
    fontWeight: "900",
    letterSpacing: -0.5,
  },
  closeButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: Radius.pill,
    backgroundColor: "#E9EFEC",
  },
  closeText: { color: Palette.muted, fontSize: 12, fontWeight: "800" },
  infoCard: {
    padding: 16,
    borderWidth: 1,
    borderColor: "#E1E8E4",
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
  },
  infoRow: { flexDirection: "row", alignItems: "flex-start", gap: 14 },
  infoLabel: {
    width: 58,
    color: Palette.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  infoValue: {
    minWidth: 0,
    flex: 1,
    color: Palette.ink,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 19,
  },
  link: { color: Palette.accent },
  divider: { height: 1, marginVertical: 12, backgroundColor: "#EDF1EF" },
  sectionTitle: {
    marginBottom: 10,
    color: Palette.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  tag: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    overflow: "hidden",
    borderRadius: Radius.pill,
    backgroundColor: "#E4F2EE",
    color: Palette.accent,
    fontSize: 11,
    fontWeight: "800",
  },
  notice: {
    padding: 14,
    borderRadius: Radius.small,
    backgroundColor: "#F0F3F1",
    color: Palette.muted,
    fontSize: 12,
    lineHeight: 18,
  },
  externalError: {
    color: Palette.danger,
    fontSize: 11,
    fontWeight: "700",
    textAlign: "center",
  },
  primaryActions: { gap: 8 },
  primaryButton: {
    minHeight: 52,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.medium,
    backgroundColor: Palette.accent,
  },
  primaryButtonText: { color: "#FFFFFF", fontSize: 14, fontWeight: "900" },
  primaryButtonCaption: {
    marginTop: 3,
    color: "#D7F0EB",
    fontSize: 10,
    fontWeight: "700",
  },
  secondaryButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#C9D8D3",
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
  },
  secondaryButtonText: {
    color: Palette.accent,
    fontSize: 13,
    fontWeight: "800",
  },
  utilityActions: { flexDirection: "row", gap: 8 },
  utilityButton: {
    flex: 1,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  utilityText: {
    color: Palette.muted,
    fontSize: 12,
    fontWeight: "800",
    textDecorationLine: "underline",
  },
  webDetailScreen: { flex: 1, backgroundColor: Palette.surface },
  webDetailHeader: {
    minHeight: 68,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#E1E8E4",
  },
  webDetailHeading: { minWidth: 0, flex: 1 },
  webDetailTitle: { color: Palette.ink, fontSize: 17, fontWeight: "900" },
  webDetailCaption: {
    marginTop: 3,
    color: Palette.muted,
    fontSize: 10,
    fontWeight: "700",
  },
  webDetail: { width: "100%", backgroundColor: "#FFFFFF" },
  webDetailLoading: {
    position: "absolute",
    inset: 0,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    backgroundColor: "#FFFFFF",
  },
  webDetailFallback: {
    minHeight: 260,
    alignItems: "stretch",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  webDetailFallbackTitle: {
    color: Palette.ink,
    fontSize: 17,
    fontWeight: "900",
    textAlign: "center",
  },
  webDetailFallbackText: {
    color: Palette.muted,
    fontSize: 12,
    lineHeight: 18,
    textAlign: "center",
  },
});
