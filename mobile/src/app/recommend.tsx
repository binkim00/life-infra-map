import { router, useLocalSearchParams } from "expo-router";
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
import { PlaceMap } from "@/components/place-map";
import { Screen, ui } from "@/components/screen";
import type { Place } from "@/types/place";

type AiPlace = Place & {
  source?: string;
  external_id?: string;
  place_id?: number;
  recommendation_reason?: string;
  suggested_tags?: string[];
  distance_m?: number;
};
type AiResponse = {
  results?: AiPlace[];
  message?: string;
  clarification_question?: string;
  search_plan?: Record<string, unknown>;
};

export default function RecommendScreen() {
  const params = useLocalSearchParams<{ q?: string }>();
  const { requireLogin, isLoggedIn } = useAuth();
  const [query, setQuery] = useState(params.q || "");
  const [submitted, setSubmitted] = useState(params.q || "");
  const [results, setResults] = useState<AiPlace[]>([]);
  const [selected, setSelected] = useState<AiPlace | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(Boolean(params.q));
  const [searchPlan, setSearchPlan] = useState<Record<string, unknown> | null>(
    null,
  );
  const [webResults, setWebResults] = useState<AiPlace[]>([]);
  const search = (next = query) => {
    if (!next.trim()) return;
    setMessage("");
    setLoading(true);
    setSubmitted(next.trim());
  };
  useEffect(() => {
    if (!submitted) return;
    recommendationApi
      .aiSearch({
        query: submitted,
        lat: 37.5665,
        lng: 126.978,
        limit: 10,
        previous_search_context: searchPlan,
      })
      .then((raw) => {
        const data = raw as AiResponse;
        const places = data.results || [];
        setResults(places);
        setSelected(places[0] || null);
        setSearchPlan(data.search_plan || null);
        setWebResults([]);
        if (isLoggedIn)
          void recommendationApi.saveSearchLog({
            query: submitted,
            search_mode: "recommendation_query",
            scenario: data.clarification_question
              ? "ask_clarification"
              : "ai_place_search",
            lat: 37.5665,
            lng: 126.978,
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
  }, [submitted]);
  const searchWeb = async () => {
    try {
      setLoading(true);
      const raw = await recommendationApi.aiWebSearch({
        query: submitted,
        lat: 37.5665,
        lng: 126.978,
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
            : "웹 참고 후보가 없습니다."),
      );
    } catch {
      setMessage("웹 참고 검색에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };
  const save = async () => {
    if (!selected || !requireLogin()) return;
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
  };
  const openMap = () => {
    if (!selected) return;
    Linking.openURL(
      selected.place_url ||
        selected.kakao_place_url ||
        `https://map.kakao.com/link/map/${encodeURIComponent(selected.name)},${selected.lat},${selected.lng}`,
    );
  };
  return (
    <View style={styles.root}>
      <Screen
        title="AI 장소 추천"
        subtitle="상황과 조건을 이해해 결과를 정렬합니다."
        back
      >
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
                  <Pressable onPress={openMap} style={ui.buttonSecondary}>
                    <Text style={ui.buttonSecondaryText}>지도</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}
            {selected ? (
              <View style={ui.row}>
                <Pressable onPress={save} style={[ui.buttonSecondary, ui.grow]}>
                  <Text style={ui.buttonSecondaryText}>저장</Text>
                </Pressable>
                <Pressable
                  onPress={() =>
                    requireLogin() &&
                    router.push({
                      pathname: "/place-report",
                      params: {
                        placeId: String(selected.place_id || selected.id),
                        name: selected.name,
                        address: selected.address || "",
                        lat: String(selected.lat),
                        lng: String(selected.lng),
                      },
                    })
                  }
                  style={[ui.buttonSecondary, ui.grow]}
                >
                  <Text style={ui.buttonSecondaryText}>정보 제보</Text>
                </Pressable>
              </View>
            ) : null}
            <Pressable onPress={searchWeb} style={ui.buttonSecondary}>
              <Text style={ui.buttonSecondaryText}>웹 참고 후보 검색</Text>
            </Pressable>
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
                        {place.address} ·{" "}
                        {Math.round(place.distance_m || place.distance || 0)}m
                      </Text>
                      {place.recommendation_reason ? (
                        <Text style={styles.reason}>
                          {place.recommendation_reason}
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
  map: { overflow: "hidden", borderRadius: 20, backgroundColor: "#FFFFFF" },
  mapFooter: {
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
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
});
