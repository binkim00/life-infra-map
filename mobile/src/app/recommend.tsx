import { router, useLocalSearchParams } from "expo-router";
import { searchLocation } from "@/utils/location";
import { useEffect, useRef, useState } from "react";
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
import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/auth-context";
import { PlaceDetailSheet } from "@/components/place-detail-sheet";
import { PlaceMap } from "@/components/place-map";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import type { Place } from "@/types/place";

type AiPlace = Place & {
  source?: string;
  external_id?: string;
  place_id?: number;
  recommendation_reason?: string;
  historical_tags?: string[];
  historical_evidence_label?: string;
  result_tier?: "all_conditions_met" | "partial_match" | "best_available";
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
  clarification_options?: (string | { label?: string; value?: string })[];
  decision_action?: string;
  search_plan?: Record<string, unknown>;
  result_quality?: {
    returned_count?: number;
    all_conditions_met?: number;
    partial_match?: number;
    best_available?: number;
  };
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

type ConversationSession = {
  id: string;
  token: string;
};

const GREETING =
  "어떤 상황에서 갈 장소를 찾고 있나요? 지역, 동행, 목적이나 꼭 필요한 조건을 편하게 말해 주세요.";

const sourceLabel = (place: AiPlace) => {
  if (place.source_label) return place.source_label;
  const source = String(place.source_name || place.source || place.result_source || "");
  if (source.includes("kakao")) return "카카오 장소";
  if (source.includes("web")) return "웹 조사 후보";
  return "LifeMap 저장 장소";
};

const optionValue = (
  option: NonNullable<AiResponse["clarification_options"]>[number],
) => (typeof option === "string" ? option : option.value || option.label || "");

const optionLabel = (
  option: NonNullable<AiResponse["clarification_options"]>[number],
) => (typeof option === "string" ? option : option.label || option.value || "");

const assistantText = (data: AiResponse, count: number) => {
  if (data.clarification_question) return data.clarification_question;
  if (data.message) return data.message;
  if (data.decision_action === "search") {
    if (!count)
      return "말씀한 조건을 모두 확인했지만, 지금 보여드릴 만한 장소를 찾지 못했어요. 지역을 넓히거나 꼭 필요한 조건 하나를 덜어볼까요?";
    const exact = data.result_quality?.all_conditions_met || 0;
    const fallback = data.result_quality?.best_available || 0;
    if (!exact && fallback === data.result_quality?.returned_count)
      return `요청한 조건을 직접 확인할 수 있는 장소는 아직 없어요. 대신 지역과 장소 종류가 맞는 가까운 후보 ${count}곳만 보여드릴게요. 카드의 ‘확인 필요’ 조건을 꼭 봐 주세요.`;
    return exact
      ? `조건을 잘 충족하는 장소 ${exact}곳을 포함해 ${count}곳을 찾았어요.`
      : `${count}곳을 찾았어요. 확인 가능한 근거와 거리를 기준으로 가까운 후보부터 보여드릴게요.`;
  }
  return "말씀하신 내용을 반영했어요.";
};

const resolvedLocationLabel = (searchPlan?: Record<string, unknown>) => {
  const rawFrame =
    searchPlan?.place_intent_frame ?? searchPlan?.placeIntentFrame;
  if (!rawFrame || typeof rawFrame !== "object") return null;
  const frame = rawFrame as Record<string, unknown>;
  const locationMode = String(frame.location_mode ?? frame.locationMode ?? "");
  const anchor = String(
    frame.anchor_location ?? frame.anchorLocation ?? "",
  ).trim();
  return locationMode === "explicit" && anchor ? `${anchor} 기준` : null;
};

const formatDistance = (place: AiPlace) => {
  const distance = place.distance_m ?? place.distance;
  if (distance === undefined || distance === null || distance <= 0)
    return "거리 정보 없음";
  return distance < 1000
    ? `${Math.round(distance)}m`
    : `${(distance / 1000).toFixed(1)}km`;
};

export default function RecommendScreen() {
  const params = useLocalSearchParams<{
    q?: string;
    lat?: string;
    lng?: string;
  }>();
  const { requireLogin, isLoggedIn } = useAuth();
  const initialLat = Number(params.lat);
  const initialLng = Number(params.lng);
  const hasInitialCenter =
    Number.isFinite(initialLat) && Number.isFinite(initialLng);
  const [query, setQuery] = useState(params.q || "");
  const [deviceLocation, setDeviceLocation] = useState<{ lat: number; lng: number } | null>(null);
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
  const [loading, setLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState<"" | "save" | "map">("");
  const [searchPlan, setSearchPlan] = useState<Record<string, unknown> | null>(
    null,
  );
  const [locationBasisLabel, setLocationBasisLabel] = useState<string | null>(
    null,
  );
  const [webResults, setWebResults] = useState<AiPlace[]>([]);
  const [canSearchWeb, setCanSearchWeb] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { id: "greeting", role: "assistant", text: GREETING },
  ]);
  const [clarificationOptions, setClarificationOptions] = useState<
    NonNullable<AiResponse["clarification_options"]>
  >([]);
  const sessionRef = useRef<ConversationSession | null>(null);
  const initialQuerySentRef = useRef(false);
  const needsWebFallback =
    results.length < 5 ||
    results
      .slice(0, 5)
      .every((place) =>
        ["empty", "thin"].includes(place.evidence_quality_level || "empty"),
      );
  const createSession = async () => {
    const raw = await recommendationApi.createConversationSession();
    const session = {
      id: String(raw.id || ""),
      token: String(raw.conversation_token || ""),
    };
    if (!session.id) throw new Error("conversation_session_missing");
    sessionRef.current = session;
    return session;
  };

  const submitTurn = async (next: string) => {
    const text = next.trim();
    if (!text || loading) return;
    setQuery("");
    setMessage("");
    setLoading(true);
    setClarificationOptions([]);
    setChatMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", text },
    ]);
    try {
      const session = sessionRef.current || (await createSession());
      // Keep the session even after conflicts; creating a replacement here
      // would silently discard earlier constraints.
      const raw = await recommendationApi.sendConversationTurn(
        session.id,
        session.token,
        { query: text, lat: center.lat, lng: center.lng, limit: 10 },
      );
      const data = raw as AiResponse;
      const receivedPlaces = data.results || [];
      const supportedPlaces = receivedPlaces.filter(
        (place) => place.result_tier !== "best_available",
      );
      const fallbackPlaces = receivedPlaces.filter(
        (place) => place.result_tier === "best_available",
      );
      const allFallback =
        receivedPlaces.length > 0 &&
        data.result_quality?.best_available === receivedPlaces.length;
      const places = allFallback
        ? receivedPlaces.slice(0, 5)
        : supportedPlaces.length >= 3
          ? supportedPlaces.slice(0, 10)
          : [
              ...supportedPlaces,
              ...fallbackPlaces.slice(
                0,
                Math.max(0, 3 - supportedPlaces.length),
              ),
            ];
      const action = data.decision_action || "";
      if (action !== "ask_clarification") {
        setResults(places);
        setSelected(places[0] || null);
        setWebResults([]);
      }
      setCanSearchWeb(action === "search");
      setSearchPlan(data.search_plan || null);
      setLocationBasisLabel(resolvedLocationLabel(data.search_plan));
      setClarificationOptions(data.clarification_options || []);
      setChatMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          text: assistantText(data, places.length),
        },
      ]);
      if (isLoggedIn)
        void recommendationApi.saveSearchLog({
          query: text,
          search_mode: "recommendation_query",
          scenario: action || "ai_place_search",
          lat: center.lat,
          lng: center.lng,
          target_query: text,
          result_count: places.length,
          db_result_count: places.filter((place) => place.source === "db")
            .length,
          kakao_result_count: places.filter((place) => place.source !== "db")
            .length,
          ai_web_result_count: 0,
          search_plan_snapshot: data.search_plan || {},
        });
    } catch (error) {
      setQuery(text);
      setChatMessages((current) => [
        ...current,
        {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          text:
            error instanceof ApiError && error.status === 404
              ? "이전 대화를 찾을 수 없습니다. 새 대화를 시작한 뒤 지역과 원하는 조건을 다시 알려주세요."
              : "대화를 이어가지 못했어요. 입력한 내용은 남겨두었습니다. 잠시 후 다시 보내 주세요.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const search = (next = query) => void submitTurn(next);

  useEffect(() => {
    void createSession()
      .then(() => {
        if (params.q && !initialQuerySentRef.current) {
          initialQuerySentRef.current = true;
          void submitTurn(params.q);
        }
      })
      .catch(() =>
        setMessage("대화 준비에 실패했습니다. 검색을 누르면 다시 연결합니다."),
      );
    // 새 화면마다 독립된 대화를 시작합니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resetConversation = async () => {
    const previous = sessionRef.current;
    sessionRef.current = null;
    setResults([]);
    setSelected(null);
    setSearchPlan(null);
    setWebResults([]);
    setCanSearchWeb(false);
    setClarificationOptions([]);
    setLocationBasisLabel(null);
    setChatMessages([
      { id: `greeting-${Date.now()}`, role: "assistant", text: GREETING },
    ]);
    setMessage("");
    if (previous)
      void recommendationApi
        .closeConversationSession(previous.id, previous.token)
        .catch(() => undefined);
    try {
      await createSession();
    } catch {
      setMessage(
        "새 대화를 준비하지 못했습니다. 첫 메시지를 보내면 다시 시도합니다.",
      );
    }
  };

  const applyCurrentLocation = async () => {
    try {
      const coordinates = await searchLocation();
      if (!coordinates) {
        setMessage("현재 위치를 사용하려면 위치 권한이 필요합니다.");
        return;
      }
      setDeviceLocation({ lat: coordinates.latitude, lng: coordinates.longitude });
      setCenter({
        lat: coordinates.latitude,
        lng: coordinates.longitude,
        label: "현재 위치 기준",
      });
      setLocationBasisLabel(null);
      setMessage(
        "현재 위치를 기준으로 설정했습니다. 원하는 장소나 조건을 말해 주세요.",
      );
    } catch {
      setMessage(
        "현재 위치를 확인하지 못했습니다. 동네나 역 이름을 입력해 주세요.",
      );
    }
  };
  useEffect(() => {
    if (hasInitialCenter) return;
    let active = true;
    void searchLocation()
      .then((coordinates) => {
        if (!active || !coordinates) return;
        setDeviceLocation({ lat: coordinates.latitude, lng: coordinates.longitude });
        setCenter({
          lat: coordinates.latitude,
          lng: coordinates.longitude,
          label: "현재 위치 기준",
        });
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [hasInitialCenter]);
  const searchWeb = async () => {
    try {
      setLoading(true);
      const raw = await recommendationApi.aiWebSearch({
        query:
          chatMessages.filter((item) => item.role === "user").at(-1)?.text ||
          "",
        lat: center.lat,
        lng: center.lng,
        search_plan: searchPlan || {},
        condition: {},
        existing_results_summary: { count: results.length },
      });
      const envelope = raw as {
        ai_web_search?: {
          candidates?: AiPlace[];
          results?: AiPlace[];
          error?: string;
        };
        candidates?: AiPlace[];
        results?: AiPlace[];
        error?: string;
      };
      const data = envelope.ai_web_search || envelope;
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
    if (!selected || actionBusy || !requireLogin()) return;
    try {
      setActionBusy("save");
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
    } finally {
      setActionBusy("");
    }
  };
  const openMap = async () => {
    if (!selected || actionBusy) return;
    const coordinatesAvailable = Number.isFinite(Number(selected.lat)) && Number.isFinite(Number(selected.lng));
    const url = selected.place_url || selected.kakao_place_url || (coordinatesAvailable
      ? `https://map.kakao.com/link/map/${encodeURIComponent(selected.name)},${selected.lat},${selected.lng}`
      : "");
    if (!url) {
      setMessage("지도에서 열 수 있는 위치 정보가 없습니다.");
      return;
    }
    try {
      setActionBusy("map");
      await Linking.openURL(url);
    } catch {
      setMessage("지도 앱을 열지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setActionBusy("");
    }
  };
  const report = () => {
    if (!selected) return;
    setDetailVisible(false);
    router.push({
      pathname: "/place-report",
      params: {
        placeId: selected.place_id
          ? String(selected.place_id)
          : selected.source === "db"
            ? String(selected.id).replace(/^db:/, "")
            : undefined,
        name: selected.name,
        address: selected.address || "",
        lat: Number.isFinite(Number(selected.lat)) ? String(selected.lat) : undefined,
        lng: Number.isFinite(Number(selected.lng)) ? String(selected.lng) : undefined,
      },
    });
  };
  return (
    <View style={styles.root}>
      <Screen
        title="상황 맞춤 추천"
        subtitle="원하는 상황과 꼭 필요한 조건을 알려주세요. 근거를 구분해 추천합니다."
        back
        footer={
          <>
            {clarificationOptions.length ? (
              <View style={styles.optionRow}>
                {clarificationOptions.map((option, index) => (
                  <Pressable
                    key={`${optionValue(option)}-${index}`}
                    disabled={loading}
                    onPress={() => submitTurn(optionValue(option))}
                    style={styles.optionButton}
                  >
                    <Text style={styles.optionText}>{optionLabel(option)}</Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
            <View style={ui.row}>
              <TextInput
                accessibilityLabel="상황 검색 메시지"
                value={query}
                onChangeText={setQuery}
                onSubmitEditing={() => search()}
                placeholder="답변하거나 원하는 조건을 더 알려주세요"
                placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                editable={!loading}
                style={[ui.input, ui.grow]}
              />
              <Pressable
                accessibilityRole="button"
                onPress={() => search()}
                disabled={loading || !query.trim()}
                style={[
                  ui.button,
                  (loading || !query.trim()) && styles.disabledButton,
                ]}
              >
                <Text style={ui.buttonText}>보내기</Text>
              </Pressable>
            </View>
          </>
        }
      >
        <Pressable
          onPress={() => router.push("/explore")}
          style={styles.modeLink}
        >
          <Text style={styles.modeLinkText}>
            장소명·업종만 찾는다면 일반 장소 검색으로 이동
          </Text>
        </Pressable>
        <Pressable
          onPress={() => void applyCurrentLocation()}
          style={styles.locationButton}
        >
          <Text style={styles.locationButtonText}>
            {locationBasisLabel || center.label}
          </Text>
        </Pressable>
        <View style={styles.chatHeader}>
          <Text style={styles.chatTitle}>대화</Text>
          <Pressable onPress={resetConversation} disabled={loading}>
            <Text style={styles.resetText}>새 대화</Text>
          </Pressable>
        </View>
        {chatMessages.length === 1 && !results.length && !loading ? (
          <View style={styles.welcomeCard}>
            <View style={styles.mascotWrap}>
              <View style={styles.mascotBody}>
                <View style={styles.mascotEyeLeft} /><View style={styles.mascotEyeRight} />
                <View style={styles.mascotSmile} />
              </View>
              <View style={styles.mascotPin}><Text style={styles.mascotPinText}>●</Text></View>
            </View>
            <Text style={styles.welcomeTitle}>어떤 하루를 보내고 싶나요?</Text>
            <Text style={styles.welcomeText}>{GREETING}</Text>
            <View style={styles.quickPrompts}>
              {["서면에서 조용한 카페", "주차 가능한 가족 식당", "잠깐 쉬기 좋은 곳"].map((prompt) => (
                <Pressable key={prompt} onPress={() => void submitTurn(prompt)} style={styles.quickPrompt}>
                  <Text style={styles.quickPromptText}>{prompt}</Text><Text style={styles.quickPromptArrow}>›</Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : <View style={styles.chat}>
          {chatMessages.map((item) => (
            <View
              key={item.id}
              style={[
                styles.bubble,
                item.role === "user"
                  ? styles.userBubble
                  : styles.assistantBubble,
              ]}
            >
              <Text
                style={
                  item.role === "user" ? styles.userText : styles.assistantText
                }
              >
                {item.text}
              </Text>
            </View>
          ))}
          {loading ? (
            <View
              style={[
                styles.bubble,
                styles.assistantBubble,
                styles.typingBubble,
              ]}
            >
              <ActivityIndicator size="small" color="#0F766E" />
              <Text style={styles.assistantText}>조건을 이해하고 있어요…</Text>
            </View>
          ) : null}
        </View>}
        {message ? (
          <Text style={message.includes("실패") ? ui.error : ui.success}>
            {message}
          </Text>
        ) : null}
        {(
          <>
            {selected ? (
              <View style={styles.map}>
                <PlaceMap
                  place={selected}
                  places={results}
                  currentLocation={deviceLocation}
                  onRequestCurrentLocation={() => void applyCurrentLocation()}
                  onSelectPlace={setSelected}
                />
                <View style={styles.mapFooter}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`${selected.name} 상세정보`}
                    onPress={() => setDetailVisible(true)}
                    style={ui.grow}
                  >
                    <Text style={styles.selectedName}>{selected.name}</Text>
                    <Text style={ui.muted}>{selected.address}</Text>
                  </Pressable>
                  <View style={styles.mapActions}>
                    <Pressable
                      onPress={() => setDetailVisible(true)}
                      style={ui.buttonSecondary}
                    >
                      <Text style={ui.buttonSecondaryText}>상세정보</Text>
                    </Pressable>
                    <Pressable disabled={Boolean(actionBusy)} onPress={() => void openMap()} style={ui.buttonSecondary}>
                      <Text style={ui.buttonSecondaryText}>{actionBusy === "map" ? "여는 중…" : "지도"}</Text>
                    </Pressable>
                  </View>
                </View>
              </View>
            ) : null}
            {selected ? (
              <View style={ui.row}>
                <Pressable disabled={Boolean(actionBusy)} onPress={save} style={[ui.buttonSecondary, ui.grow]}>
                  <Text style={ui.buttonSecondaryText}>{actionBusy === "save" ? "저장 중…" : "저장"}</Text>
                </Pressable>
                <Pressable
                  onPress={report}
                  style={[ui.buttonSecondary, ui.grow]}
                >
                  <Text style={ui.buttonSecondaryText}>정보 제보</Text>
                </Pressable>
              </View>
            ) : null}
            {canSearchWeb && needsWebFallback ? (
              <Pressable onPress={searchWeb} style={ui.buttonSecondary}>
                <Text style={ui.buttonSecondaryText}>부족한 결과 보강하기</Text>
              </Pressable>
            ) : null}
            <View style={styles.list}>
              {results.map((place, index) => (
                <Pressable
                  key={`${place.source || place.result_source || "place"}:${place.id}`}
                  accessibilityRole="button"
                  accessibilityLabel={`${place.name} 상세정보`}
                  onPress={() => {
                    setSelected(place);
                    setDetailVisible(true);
                  }}
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
                      <Text style={ui.muted}>출처: {sourceLabel(place)}</Text>
                      {place.recommendation_reason ? (
                        <Text style={styles.reason}>
                          {place.recommendation_reason}
                        </Text>
                      ) : null}
                      {place.historical_tags?.length ? (
                        <Text style={ui.muted}>과거 자료·현재 미확인: {place.historical_tags.join(", ")}. 필수 조건 충족을 뜻하지 않습니다.</Text>
                      ) : null}
                      {place.result_tier_label ? (
                        <Text style={ui.muted}>{place.result_tier_label}</Text>
                      ) : null}
                      {place.matched_conditions?.length ? (
                        <View style={styles.conditionBlock}>
                          <Text style={styles.conditionLabel}>✓ 근거 있음</Text>
                          <Text style={styles.tags}>{place.matched_conditions.slice(0, 3).join(" · ")}</Text>
                        </View>
                      ) : null}
                      {place.missing_conditions?.length ? (
                        <View style={[styles.conditionBlock, styles.missingBlock]}>
                          <Text style={styles.missingLabel}>? 확인 필요</Text>
                          <Text style={styles.missing}>{place.missing_conditions.slice(0, 3).join(" · ")}</Text>
                        </View>
                      ) : null}
                      {(["empty", "thin"] as const).includes(
                        place.evidence_quality_level as "empty" | "thin",
                      ) && place.evidence_gaps?.length ? (
                        <Text style={styles.missing}>
                          장소 정보 부족:{" "}
                          {place.evidence_gaps.slice(0, 3).join(" · ")}
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
    </View>
  );
}
const styles = StyleSheet.create({
  root: { flex: 1 },
  chatHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  chatTitle: { color: "#222222", fontSize: 16, fontWeight: "900" },
  resetText: { color: "#0F766E", fontSize: 12, fontWeight: "800" },
  chat: { gap: 8 },
  welcomeCard: { padding: 20, alignItems: "center", borderWidth: 1, borderColor: "#D9E8E3", borderRadius: 22, backgroundColor: "#F5FBF9" },
  mascotWrap: { width: 94, height: 82, position: "relative", alignItems: "center", justifyContent: "flex-end" },
  mascotBody: { width: 69, height: 61, position: "relative", borderTopLeftRadius: 34, borderTopRightRadius: 34, borderBottomLeftRadius: 27, borderBottomRightRadius: 27, backgroundColor: "#BDE6DE" },
  mascotEyeLeft: { position: "absolute", left: 20, top: 24, width: 5, height: 7, borderRadius: 3, backgroundColor: "#17675E" },
  mascotEyeRight: { position: "absolute", right: 20, top: 24, width: 5, height: 7, borderRadius: 3, backgroundColor: "#17675E" },
  mascotSmile: { position: "absolute", left: 30, top: 35, width: 11, height: 6, borderBottomWidth: 2, borderColor: "#17675E", borderRadius: 8 },
  mascotPin: { position: "absolute", right: 4, top: 0, width: 30, height: 34, alignItems: "center", justifyContent: "center", borderTopLeftRadius: 15, borderTopRightRadius: 15, borderBottomLeftRadius: 15, backgroundColor: "#FF765E", transform: [{ rotate: "45deg" }] },
  mascotPinText: { color: "#FFFFFF", fontSize: 7 },
  welcomeTitle: { marginTop: 13, color: "#17201D", fontSize: 18, fontWeight: "900" },
  welcomeText: { marginTop: 7, color: "#5F6B66", fontSize: 12, lineHeight: 19, textAlign: "center" },
  quickPrompts: { width: "100%", marginTop: 16, gap: 7 },
  quickPrompt: { minHeight: 43, paddingHorizontal: 13, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderRadius: 12, backgroundColor: "#FFFFFF" },
  quickPromptText: { color: "#31504A", fontSize: 11.5, fontWeight: "800" },
  quickPromptArrow: { color: "#0F857A", fontSize: 20 },
  bubble: {
    maxWidth: "86%",
    paddingHorizontal: 14,
    paddingVertical: 11,
    borderRadius: 16,
  },
  userBubble: {
    alignSelf: "flex-end",
    backgroundColor: "#0F766E",
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    alignSelf: "flex-start",
    backgroundColor: "#FFFFFF",
    borderBottomLeftRadius: 4,
  },
  userText: { color: "#FFFFFF", fontSize: 13, lineHeight: 19 },
  assistantText: { color: "#303633", fontSize: 13, lineHeight: 19 },
  typingBubble: { flexDirection: "row", alignItems: "center", gap: 8 },
  optionRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  optionButton: {
    paddingHorizontal: 13,
    paddingVertical: 9,
    borderWidth: 1,
    borderColor: "#8CBEB1",
    borderRadius: 999,
    backgroundColor: "#F3FAF8",
  },
  optionText: { color: "#0F766E", fontSize: 12, fontWeight: "800" },
  disabledButton: { opacity: 0.45 },
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
  conditionBlock: { marginTop: 9, padding: 9, borderRadius: 10, backgroundColor: "#E9F5F2" },
  missingBlock: { backgroundColor: "#FFF7E6" },
  conditionLabel: { color: "#0F857A", fontSize: 10, fontWeight: "900" },
  missingLabel: { color: "#B7791F", fontSize: 10, fontWeight: "900" },
});
