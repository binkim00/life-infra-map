import { router, useLocalSearchParams } from "expo-router";
import * as Location from "expo-location";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { useAuth } from "@/auth/auth-context";
import { BottomNav } from "@/components/bottom-nav";
import { PlaceDetailSheet } from "@/components/place-detail-sheet";
import { PlaceMap } from "@/components/place-map";
import { Screen, ui } from "@/components/screen";
import type { Place } from "@/types/place";

type AiPlace = Place & {
  source?: string;
  external_id?: string;
  place_id?: number;
  recommendation_reason?: string;
  result_tier_label?: string;
  matched_conditions?: string[];
  missing_conditions?: string[];
  evidence_gaps?: string[];
  evidence_quality_level?: "empty" | "thin" | "searchable" | "rich";
  suggested_tags?: string[];
  distance_m?: number;
};
type AiResponse = {
  results?: AiPlace[];
  message?: string;
  clarification_question?: string;
  search_plan?: Record<string, unknown>;
};

const resolvedLocationLabel = (searchPlan?: Record<string, unknown>) => {
  const rawFrame = searchPlan?.place_intent_frame ?? searchPlan?.placeIntentFrame;
  if (!rawFrame || typeof rawFrame !== "object") return null;
  const frame = rawFrame as Record<string, unknown>;
  const locationMode = String(
    frame.location_mode ?? frame.locationMode ?? "",
  );
  const anchor = String(
    frame.anchor_location ?? frame.anchorLocation ?? "",
  ).trim();
  return locationMode === "explicit" && anchor ? `${anchor} 기준` : null;
};

const formatDistance = (place: AiPlace) => {
  const distance = place.distance_m ?? place.distance;
  if (distance === undefined || distance === null) return "거리 정보 없음";
  return distance < 1000
    ? `${Math.round(distance)}m`
    : `${(distance / 1000).toFixed(1)}km`;
};

export default function RecommendScreen() {
  const params = useLocalSearchParams<{ q?: string; lat?: string; lng?: string }>();
  const { requireLogin, isLoggedIn } = useAuth();
  const initialLat = Number(params.lat);
  const initialLng = Number(params.lng);
  const hasInitialCenter =
    Number.isFinite(initialLat) && Number.isFinite(initialLng);
  const [query, setQuery] = useState(params.q || "");
  const [submitted, setSubmitted] = useState(params.q || "");
  const [searchRequestId, setSearchRequestId] = useState(params.q ? 1 : 0);
  const [center, setCenter] = useState<{
    lat: number | null;
    lng: number | null;
    label: string;
  }>({
    lat: hasInitialCenter ? initialLat : null,
    lng: hasInitialCenter ? initialLng : null,
    label: hasInitialCenter ? "현재 위치 기준" : "지역 제한 없음",
  });
  const [results, setResults] = useState<AiPlace[]>([]);
  const [selected, setSelected] = useState<AiPlace | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(Boolean(params.q));
  const [searchPlan, setSearchPlan] = useState<Record<string, unknown> | null>(
    null,
  );
  const [locationBasisLabel, setLocationBasisLabel] = useState<string | null>(
    null,
  );
  const [webResults, setWebResults] = useState<AiPlace[]>([]);
  const needsWebFallback =
    results.length < 5 ||
    results.slice(0, 5).every((place) =>
      ["empty", "thin"].includes(place.evidence_quality_level || "empty"),
    );
  const search = (next = query) => {
    if (!next.trim()) return;
    setMessage("");
    setLoading(true);
    setLocationBasisLabel(null);
    setSubmitted(next.trim());
    setSearchRequestId((value) => value + 1);
  };
  useEffect(() => {
    if (!submitted || !searchRequestId) return;
    recommendationApi
      .aiSearch({
        query: submitted,
        lat: center.lat,
        lng: center.lng,
        limit: 30,
        previous_search_context: searchPlan,
      })
      .then((raw) => {
        const data = raw as AiResponse;
        const places = data.results || [];
        setResults(places);
        setSelected(places[0] || null);
        setSearchPlan(data.search_plan || null);
        setLocationBasisLabel(resolvedLocationLabel(data.search_plan));
        setWebResults([]);
        if (isLoggedIn)
          void recommendationApi.saveSearchLog({
            query: submitted,
            search_mode: "recommendation_query",
            scenario: data.clarification_question
              ? "ask_clarification"
              : "ai_place_search",
            lat: center.lat,
            lng: center.lng,
            target_query: submitted,
            result_count: places.length,
            db_result_count: places.filter((place) => place.source === "db")
              .length,
            kakao_result_count: places.filter((place) => place.source !== "db")
              .length,
            ai_web_result_count: 0,
            search_plan_snapshot: data.search_plan || {},
          });
        setMessage(
          data.clarification_question ||
            data.message ||
            (!places.length ? "조건에 맞는 추천 결과가 없습니다." : ""),
        );
      })
      .catch(() => setMessage("AI 추천 검색에 실패했습니다."))
      .finally(() => setLoading(false));
    // submitted query controls requests; searchPlan is the previous conversational context.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submitted, searchRequestId, center.lat, center.lng]);

  const useCurrentLocation = async () => {
    const permission = await Location.requestForegroundPermissionsAsync();
    if (!permission.granted) {
      setMessage("현재 위치를 사용하려면 위치 권한이 필요합니다.");
      return;
    }
    const position = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });
    setCenter({
      lat: position.coords.latitude,
      lng: position.coords.longitude,
      label: "현재 위치 기준",
    });
    setLocationBasisLabel(null);
    if (submitted) setSearchRequestId((value) => value + 1);
  };
  const searchWeb = async () => {
    try {
      setLoading(true);
      const raw = await recommendationApi.aiWebSearch({
        query: submitted,
        lat: center.lat,
        lng: center.lng,
        search_plan: searchPlan || {},
        condition: {},
        existing_results_summary: { count: results.length },
      });
      const data = raw as {
        candidates?: AiPlace[];
        results?: AiPlace[];
        error?: string;
      };
      const next = data.candidates || data.results || [];
      setWebResults(next);
      setMessage(
        data.error ||
          (next.length
            ? "웹 참고 후보를 불러왔습니다."
            : "추가로 확인된 후보는 없습니다. 현재 결과의 확인 필요 조건을 참고해 주세요."),
      );
    } catch {
      setMessage("웹 참고 검색에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };
  const save = async () => {
    if (!selected || !requireLogin()) return;
    try {
      await recommendationApi.savePlace({
        placeKey: `${selected.source || "db"}:${selected.external_id || selected.place_id || selected.id}`,
        placeId:
          selected.place_id ||
          Number(String(selected.id).replace("db:", "")) ||
          null,
        externalId: selected.external_id || "",
        source: selected.source || "db",
        name: selected.name,
        category: selected.category,
        address: selected.address,
        lat: selected.lat,
        lng: selected.lng,
        detailUrl: selected.place_url || "",
        kakaoPlaceUrl: selected.kakao_place_url || "",
        raw: {},
      });
      setMessage("장소를 저장했습니다.");
    } catch {
      setMessage("장소를 저장하지 못했습니다. 다시 시도해 주세요.");
    }
  };
  const openMap = () => {
    if (!selected) return;
    Linking.openURL(
      selected.place_url ||
        selected.kakao_place_url ||
        `https://map.kakao.com/link/map/${encodeURIComponent(selected.name)},${selected.lat},${selected.lng}`,
    );
  };
  const report = () => {
    if (!selected || !requireLogin()) return;
    setDetailVisible(false);
    router.push({
      pathname: "/place-report",
      params: {
        placeId: String(selected.place_id || selected.id),
        name: selected.name,
        address: selected.address || "",
        lat: String(selected.lat),
        lng: String(selected.lng),
      },
    });
  };
  return (
    <View style={styles.root}>
      <Screen
        title="상황 기반 장소 추천"
        subtitle="상황과 조건을 이해해 이유가 있는 결과를 정렬합니다."
        back
      >
        <Pressable
          onPress={() => router.push("/explore")}
          style={styles.modeLink}
        >
          <Text style={styles.modeLinkText}>
            장소명·업종만 찾는다면 일반 장소 검색으로 이동
          </Text>
        </Pressable>
        <Pressable onPress={useCurrentLocation} style={styles.locationButton}>
          <Text style={styles.locationButtonText}>
            {locationBasisLabel || center.label}
          </Text>
        </Pressable>
        <View style={ui.row}>
          <TextInput
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => search()}
            placeholder="예: 조용히 쉴 수 있는 가까운 공원"
            style={[ui.input, ui.grow]}
          />
          <Pressable onPress={() => search()} style={ui.button}>
            <Text style={ui.buttonText}>검색</Text>
          </Pressable>
        </View>
        {message ? (
          <Text style={message.includes("실패") ? ui.error : ui.success}>
            {message}
          </Text>
        ) : null}
        {loading ? (
          <View style={styles.loading}>
            <ActivityIndicator color="#0F766E" />
            <Text style={ui.muted}>조건을 분석하고 있습니다.</Text>
          </View>
        ) : (
          <>
            {selected ? (
              <View style={styles.map}>
                <PlaceMap
                  place={selected}
                  places={results}
                  onSelectPlace={setSelected}
                />
                <View style={styles.mapFooter}>
                  <View style={ui.grow}>
                    <Text style={styles.selectedName}>{selected.name}</Text>
                    <Text style={ui.muted}>{selected.address}</Text>
                  </View>
                  <View style={styles.mapActions}>
                    <Pressable
                      onPress={() => setDetailVisible(true)}
                      style={ui.buttonSecondary}
                    >
                      <Text style={ui.buttonSecondaryText}>상세정보</Text>
                    </Pressable>
                    <Pressable onPress={openMap} style={ui.buttonSecondary}>
                      <Text style={ui.buttonSecondaryText}>지도</Text>
                    </Pressable>
                  </View>
                </View>
              </View>
            ) : null}
            {selected ? (
              <View style={ui.row}>
                <Pressable onPress={save} style={[ui.buttonSecondary, ui.grow]}>
                  <Text style={ui.buttonSecondaryText}>저장</Text>
                </Pressable>
                <Pressable onPress={report} style={[ui.buttonSecondary, ui.grow]}>
                  <Text style={ui.buttonSecondaryText}>정보 제보</Text>
                </Pressable>
              </View>
            ) : null}
            {submitted && needsWebFallback ? (
              <Pressable onPress={searchWeb} style={ui.buttonSecondary}>
                <Text style={ui.buttonSecondaryText}>부족한 결과 보강하기</Text>
              </Pressable>
            ) : null}
            <View style={styles.list}>
              {results.map((place, index) => (
                <Pressable
                  key={String(place.id)}
                  onPress={() => setSelected(place)}
                  style={[ui.card, selected?.id === place.id && styles.active]}
                >
                  <View style={ui.row}>
                    <View style={styles.rank}>
                      <Text style={styles.rankText}>{index + 1}</Text>
                    </View>
                    <View style={ui.grow}>
                      <Text style={styles.name}>{place.name}</Text>
                      <Text style={ui.muted}>
                        {place.address} · {formatDistance(place)}
                      </Text>
                      {place.recommendation_reason ? (
                        <Text style={styles.reason}>
                          {place.recommendation_reason}
                        </Text>
                      ) : null}
                      {place.result_tier_label ? (
                        <Text style={ui.muted}>{place.result_tier_label}</Text>
                      ) : null}
                      {place.matched_conditions?.length ? (
                        <Text style={styles.tags}>
                          충족: {place.matched_conditions.slice(0, 3).join(" · ")}
                        </Text>
                      ) : null}
                      {place.missing_conditions?.length ? (
                        <Text style={styles.missing}>
                          확인 필요: {place.missing_conditions.slice(0, 3).join(" · ")}
                        </Text>
                      ) : null}
                      {(["empty", "thin"] as const).includes(
                        place.evidence_quality_level as "empty" | "thin",
                      ) && place.evidence_gaps?.length ? (
                        <Text style={styles.missing}>
                          장소 정보 부족: {place.evidence_gaps.slice(0, 3).join(" · ")}
                        </Text>
                      ) : null}
                      {place.suggested_tags?.length ? (
                        <Text style={styles.tags}>
                          {place.suggested_tags.slice(0, 4).join(" · ")}
                        </Text>
                      ) : null}
                    </View>
                  </View>
                </Pressable>
              ))}
            </View>
            {webResults.length ? (
              <>
                <Text style={ui.sectionTitle}>웹 참고 후보</Text>
                <View style={styles.list}>
                  {webResults.map((place) => (
                    <View key={String(place.id || place.name)} style={ui.card}>
                      <Text style={styles.name}>{place.name}</Text>
                      <Text style={ui.muted}>{place.address}</Text>
                    </View>
                  ))}
                </View>
              </>
            ) : null}
          </>
        )}
      </Screen>
      <PlaceDetailSheet
        place={selected}
        visible={detailVisible}
        onClose={() => setDetailVisible(false)}
        onSave={save}
        onReport={report}
      />
      <BottomNav />
    </View>
  );
}
const styles = StyleSheet.create({
  root: { flex: 1 },
  loading: {
    minHeight: 180,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  modeLink: {
    padding: 12,
    borderWidth: 1,
    borderColor: "#D7E4DF",
    borderRadius: 12,
    backgroundColor: "#F5FAF8",
  },
  modeLinkText: { color: "#0F766E", fontSize: 11, fontWeight: "800" },
  locationButton: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: "#E9F3EF",
  },
  locationButtonText: { color: "#0F766E", fontSize: 11, fontWeight: "800" },
  map: { overflow: "hidden", borderRadius: 20, backgroundColor: "#FFFFFF" },
  mapFooter: {
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  mapActions: { flexDirection: "row", gap: 6 },
  selectedName: {
    marginBottom: 5,
    color: "#222222",
    fontSize: 15,
    fontWeight: "900",
  },
  list: { gap: 8 },
  active: { borderColor: "#0F766E", backgroundColor: "#F3FAF8" },
  rank: {
    width: 30,
    height: 30,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 15,
    backgroundColor: "#0F766E",
  },
  rankText: { color: "#FFFFFF", fontSize: 11, fontWeight: "900" },
  name: { marginBottom: 5, color: "#222222", fontSize: 14, fontWeight: "900" },
  reason: { marginTop: 8, color: "#38403C", fontSize: 11, lineHeight: 17 },
  tags: { marginTop: 7, color: "#0F766E", fontSize: 10, fontWeight: "700" },
  missing: { marginTop: 7, color: "#A33A21", fontSize: 10, fontWeight: "700" },
});
