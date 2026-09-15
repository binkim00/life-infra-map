import { useState } from "react";
import { Pagination } from "@/components/pagination";
import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { router } from "expo-router";

import { Pressable, StyleSheet, Text, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
type Log = {
  id: number;
  query: string;
  created_at?: string;
  search_mode?: string;
};
export default function SearchHistoryScreen() {
  const [page, setPage] = useState(1);
  const [mode, setMode] = useState("all");
  const action = useAction();
  const { data: logs, loading, error, reload: load } = useResource<Log[]>(
    () => recommendationApi.searchLogs({ page, page_size: 20 }).then((data) => (data.results || []) as Log[]), [], true, String(page),
  );
  const visibleLogs = logs.filter((log) => mode === "all" || (mode === "recommend" ? log.search_mode === "recommendation_query" : log.search_mode !== "recommendation_query"));
  const rerun = (log: Log) => router.push({ pathname: log.search_mode === "recommendation_query" ? "/recommend" : "/explore", params: { q: log.query } });
  return (
    <Screen
      title="검색 기록"
      subtitle="이전 검색을 다시 실행할 수 있습니다."
      back
    >
      <View style={styles.filters}>
        {[["all", "전체"], ["place", "일반 검색"], ["recommend", "상황 추천"]].map(([value, label]) => <Pressable key={value} onPress={() => setMode(value)} style={[styles.filter, mode === value && styles.filterActive]}><Text style={[styles.filterText, mode === value && styles.filterTextActive]}>{label}</Text></Pressable>)}
      </View>
      <LoadState loading={loading} error={error} empty={!visibleLogs.length} retry={load} />
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      <View style={styles.list}>
        {visibleLogs.map((log) => (
          <View key={log.id} style={styles.historyCard}>
            <View style={styles.historyHead}>
              <View style={styles.modeIcon}><Text style={styles.modeIconText}>{log.search_mode === "recommendation_query" ? "✦" : "⌕"}</Text></View>
              <View style={ui.grow}>
                <Text style={styles.query}>{log.query}</Text>
                <Text style={ui.muted}>
                  {log.created_at
                    ? new Date(log.created_at).toLocaleString()
                    : log.search_mode}
                </Text>
              </View>
            </View>
            <View style={styles.actions}>
              <Pressable onPress={() => rerun(log)} style={styles.rerun}><Text style={styles.rerunText}>↻  다시 검색</Text></Pressable>
              <Pressable disabled={action.busy} onPress={() => action.run(async () => { await recommendationApi.deleteSearchLog(log.id); load(); })} style={styles.deleteButton}><Text style={styles.delete}>♢  삭제</Text></Pressable>
            </View>
          </View>
        ))}
      </View>
      <Pagination page={page} setPage={setPage} hasNext={logs.length === 20} loading={loading} />
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  filters: { flexDirection: "row", padding: 4, borderRadius: Radius.pill, backgroundColor: Palette.surfaceMuted },
  filter: { minHeight: 39, flex: 1, alignItems: "center", justifyContent: "center", borderRadius: Radius.pill },
  filterActive: { backgroundColor: Palette.accent }, filterText: { color: Palette.muted, fontSize: 11, fontWeight: "800" }, filterTextActive: { color: "#FFFFFF" },
  historyCard: { padding: 15, gap: 13, borderWidth: 1, borderColor: Palette.border, borderRadius: Radius.medium, backgroundColor: Palette.surface },
  historyHead: { flexDirection: "row", alignItems: "center", gap: 11 }, modeIcon: { width: 38, height: 38, alignItems: "center", justifyContent: "center", borderRadius: 13, backgroundColor: Palette.accentSoft }, modeIconText: { color: Palette.accent, fontSize: 18, fontWeight: "900" },
  query: { marginBottom: 5, color: Palette.ink, fontSize: 14, fontWeight: "900" }, actions: { flexDirection: "row", gap: 8 },
  rerun: { minHeight: 40, flex: 1, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#A6D3CA", borderRadius: 10, backgroundColor: "#F7FCFA" }, rerunText: { color: Palette.accent, fontSize: 11, fontWeight: "900" },
  deleteButton: { minHeight: 40, flex: 1, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#F3C8C2", borderRadius: 10, backgroundColor: Palette.coralSoft }, delete: { color: Palette.coral, fontSize: 11, fontWeight: "900" },
});
