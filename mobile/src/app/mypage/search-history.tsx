import { useState } from "react";
import { Pagination } from "@/components/pagination";
import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { router } from "expo-router";

import { Pressable, StyleSheet, Text, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
type Log = {
  id: number;
  query: string;
  created_at?: string;
  search_mode?: string;
};
export default function SearchHistoryScreen() {
  const [page, setPage] = useState(1);
  const action = useAction();
  const { data: logs, loading, error, reload: load } = useResource<Log[]>(
    () => recommendationApi.searchLogs({ page, page_size: 20 }).then((data) => (data.results || []) as Log[]), [], true, String(page),
  );
  return (
    <Screen
      title="검색 기록"
      subtitle="이전 검색을 다시 실행할 수 있습니다."
      back
    >
      <LoadState loading={loading} error={error} empty={!logs.length} retry={load} />
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      <View style={styles.list}>
        {logs.map((log) => (
          <View key={log.id} style={ui.card}>
            <View style={ui.row}>
              <Pressable
                style={ui.grow}
                onPress={() =>
                  router.push({
                    pathname: log.search_mode === "recommendation_query" ? "/recommend" : "/explore",
                    params: { q: log.query },
                  })
                }
              >
                <Text style={styles.query}>{log.query}</Text>
                <Text style={ui.muted}>
                  {log.created_at
                    ? new Date(log.created_at).toLocaleString()
                    : log.search_mode}
                </Text>
              </Pressable>
              <Pressable
                disabled={action.busy}
                onPress={() => action.run(async () => {
                  await recommendationApi.deleteSearchLog(log.id);
                  load();
                })}
              >
                <Text style={styles.delete}>삭제</Text>
              </Pressable>
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
  query: { marginBottom: 5, color: "#222222", fontSize: 14, fontWeight: "900" },
  delete: { color: "#B42318", fontSize: 11, fontWeight: "800" },
});
