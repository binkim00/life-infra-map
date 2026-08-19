import { router } from "expo-router";
import { useEffect, useState } from "react";
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
  const [logs, setLogs] = useState<Log[]>([]);
  const [message, setMessage] = useState("");
  const load = () =>
    recommendationApi
      .searchLogs({ page: 1, page_size: 50 })
      .then((data) => setLogs((data.results || []) as Log[]))
      .catch(() => setMessage("검색 기록을 불러오지 못했습니다."));
  useEffect(() => {
    void load();
  }, []);
  return (
    <Screen
      title="검색 기록"
      subtitle="이전 검색을 다시 실행할 수 있습니다."
      back
    >
      {message ? <Text style={ui.error}>{message}</Text> : null}
      <View style={styles.list}>
        {logs.map((log) => (
          <View key={log.id} style={ui.card}>
            <View style={ui.row}>
              <Pressable
                style={ui.grow}
                onPress={() =>
                  router.push({
                    pathname: "/explore",
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
                onPress={async () => {
                  await recommendationApi.deleteSearchLog(log.id);
                  load();
                }}
              >
                <Text style={styles.delete}>삭제</Text>
              </Pressable>
            </View>
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  query: { marginBottom: 5, color: "#222222", fontSize: 14, fontWeight: "900" },
  delete: { color: "#B42318", fontSize: 11, fontWeight: "800" },
});
