import { useState } from "react";
import { Linking, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { Screen, ui, INPUT_PLACEHOLDER_COLOR } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";

type Evidence = {
  id: number;
  place_name: string;
  address: string;
  tag: string;
  quote: string;
  source: string;
  source_url: string;
  status: string;
  polarity: string;
  note: string;
  confidence: number;
  freshness_label?: string;
  content_approved?: boolean;
  search_eligible?: boolean;
  usage_scope?: "search" | "archive_only" | "none";
};
const STATUSES = [
  ["pending", "확인 필요"],
  ["approved", "승인"],
  ["approved_limited", "제한 승인"],
  ["research", "재조사"],
  ["rejected", "반려"],
  ["all", "전체"],
] as const;
export default function EvidenceQueueScreen() {
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const action = useAction();
  const { data, loading, error, reload } = useResource(
    () =>
      recommendationApi.evidenceQueue({ status, page, ...(appliedQuery ? { q: appliedQuery } : {}) }) as Promise<{
        count: number;
        has_next: boolean;
        results: Evidence[];
      }>,
    { count: 0, has_next: false, results: [] as Evidence[] },
    true,
    `${status}:${page}:${appliedQuery}`,
  );
  const review = (item: Evidence, decision: string) =>
    action.run(async () => {
      await recommendationApi.evidenceReview(item.id, {
        status: decision,
        note: notes[item.id] || "",
      });
      await reload();
    });
  return (
    <Screen
      title="수집 근거 검토"
      subtitle="승인은 검색 근거로 사용하고, 제한 승인은 자료만 보존해 검색·필수 조건 판정에서는 제외합니다. 오래된 자료는 승인해도 현재 사실로 취급하지 않습니다."
      back
    >
      <View style={styles.searchRow}>
        <TextInput
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={() => { setAppliedQuery(query.trim()); setPage(1); }}
          placeholder="장소명, 태그, 출처 검색"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          returnKeyType="search"
          style={[ui.input, styles.grow]}
        />
        <Pressable onPress={() => { setAppliedQuery(query.trim()); setPage(1); }} style={ui.button}>
          <Text style={ui.buttonText}>검색</Text>
        </Pressable>
      </View>
      <View style={styles.statusTabs}>
        {STATUSES.map(([value, label]) => (
          <Pressable
            key={value}
            onPress={() => {
              setStatus(value);
              setPage(1);
            }}
            style={[styles.statusTab, status === value && styles.statusTabActive]}
          >
            <Text
              style={[styles.statusTabText, status === value && styles.statusTabTextActive]}
            >
              {label}
            </Text>
          </Pressable>
        ))}
      </View>
      <LoadState
        loading={loading}
        error={error}
        empty={!data.results.length}
        retry={reload}
      />
      {!loading ? (
        <View style={styles.queueSummary}><Text style={styles.queueCount}>{data.count.toLocaleString()}</Text><View><Text style={styles.queueTitle}>현재 조건의 근거</Text><Text style={styles.queueCopy}>{page}페이지 · 원문과 장소 일치를 확인한 뒤 판정하세요.</Text></View></View>
      ) : null}
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      {data.results.map((item) => (
        <View key={item.id} style={[ui.card, styles.evidenceCard]}>
          <Text style={ui.sectionTitle}>
            {item.place_name} · {item.tag}
          </Text>
          <Text style={ui.muted}>{item.address}</Text>
          <Text style={ui.muted}>
            {({ web_search: "웹 조사", naver_blog_search: "네이버 블로그", user_report: "사용자 제보" } as Record<string, string>)[item.source] || "외부 수집"} · {({ positive: "조건 뒷받침", negative: "조건 불일치", neutral: "중립" } as Record<string, string>)[item.polarity] || "판정 확인 필요"} · 수집 점수 {item.confidence}
          </Text>
          <Text>{item.quote || "인용문 없음"}</Text>
          {item.freshness_label ? <Text style={ui.muted}>{item.freshness_label}{item.search_eligible ? " · 검색 사용" : item.usage_scope === "archive_only" ? " · 자료만 보존" : ""}</Text> : null}
          {/^https?:\/\//.test(item.source_url) ? (
            <Pressable
              onPress={() => action.run(() => Linking.openURL(item.source_url))}
              style={ui.buttonSecondary}
            >
              <Text style={ui.buttonSecondaryText}>원문 열기</Text>
            </Pressable>
          ) : null}
          {item.note ? (
            <Text style={ui.muted}>이전 검토: {item.note}</Text>
          ) : null}
          <TextInput
            value={notes[item.id] || ""}
            onChangeText={(value) =>
              setNotes((current) => ({ ...current, [item.id]: value }))
            }
            placeholder="장소 일치·인용문·조건을 확인한 판정 근거 (필수)"
            placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
            multiline
            style={ui.textarea}
          />
          <View style={styles.decisionRow}>
            {[["rejected", "반려"], ["pending", "보류"], ["research", "재조사"], ["approved_limited", "제한 승인"], ["approved", "승인"]].map(([value, label]) => (
              <Pressable
                key={value}
                disabled={action.busy || !notes[item.id]?.trim()}
                onPress={() => review(item, value)}
                style={[
                  styles.decision,
                  value === "approved" && styles.approve,
                  value === "rejected" && styles.reject,
                  (action.busy || !notes[item.id]?.trim()) && styles.disabled,
                ]}
              >
                <Text style={[styles.decisionText, value === "approved" && styles.approveText, value === "rejected" && styles.rejectText]}>{label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      ))}
      <View style={ui.row}>
        <Pressable
          disabled={page === 1 || loading}
          onPress={() => setPage((p) => p - 1)}
          style={ui.buttonSecondary}
        >
          <Text>이전</Text>
        </Pressable>
        <Pressable
          disabled={!data.has_next || loading}
          onPress={() => setPage((p) => p + 1)}
          style={ui.buttonSecondary}
        >
          <Text>다음</Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  searchRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  grow: { minWidth: 0, flex: 1 },
  statusTabs: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  statusTab: { minHeight: 36, paddingHorizontal: 11, alignItems: "center", justifyContent: "center", borderRadius: Radius.pill, backgroundColor: Palette.surfaceMuted },
  statusTabActive: { backgroundColor: Palette.ink },
  statusTabText: { color: Palette.muted, fontSize: 10, fontWeight: "800" },
  statusTabTextActive: { color: "#FFFFFF" },
  queueSummary: { padding: 16, flexDirection: "row", alignItems: "center", gap: 14, borderRadius: Radius.large, backgroundColor: Palette.ink },
  queueCount: { minWidth: 62, color: "#70D4C9", fontSize: 25, fontWeight: "900" },
  queueTitle: { color: "#FFFFFF", fontSize: 13, fontWeight: "900" },
  queueCopy: { marginTop: 3, color: "#BDC8C3", fontSize: 9 },
  evidenceCard: { gap: 9 },
  decisionRow: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  decision: { minHeight: 40, paddingHorizontal: 12, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#DFE7E3", borderRadius: 12, backgroundColor: "#FFFFFF" },
  decisionText: { color: "#17201D", fontSize: 11, fontWeight: "900" },
  approve: { borderColor: "#0F857A", backgroundColor: "#0F857A" },
  approveText: { color: "#FFFFFF" },
  reject: { borderColor: "#F0BABA", backgroundColor: "#FFF0F0" },
  rejectText: { color: "#D94B4B" },
  disabled: { opacity: 0.45 },
});
