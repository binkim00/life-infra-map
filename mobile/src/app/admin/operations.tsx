import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
export default function AdminOperationsScreen() {
  const [data, setData] = useState<Record<string, unknown>>({});
  const [error, setError] = useState("");
  useEffect(() => {
    recommendationApi
      .adminOperations({ days: 7 })
      .then(setData)
      .catch(() => setError("운영 현황을 불러오지 못했습니다."));
  }, []);
  const entries = Object.entries(data).filter(([, value]) =>
    ["number", "string", "boolean"].includes(typeof value),
  );
  return (
    <Screen title="운영 현황" subtitle="최근 7일 검색·장소 데이터 상태" back>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      <View style={styles.grid}>
        {entries.map(([key, value]) => (
          <View key={key} style={[ui.card, styles.metric]}>
            <Text style={styles.value}>{String(value)}</Text>
            <Text style={ui.muted}>{key.replaceAll("_", " ")}</Text>
          </View>
        ))}
      </View>
      {Object.entries(data)
        .filter(([, value]) => typeof value === "object" && value !== null)
        .map(([key, value]) => (
          <View key={key} style={ui.card}>
            <Text style={styles.heading}>{key.replaceAll("_", " ")}</Text>
            <Text style={styles.json}>{JSON.stringify(value, null, 2)}</Text>
          </View>
        ))}
    </Screen>
  );
}
const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  metric: { minWidth: 140, flex: 1 },
  value: { marginBottom: 5, color: "#0F766E", fontSize: 24, fontWeight: "900" },
  heading: {
    marginBottom: 10,
    color: "#222222",
    fontSize: 14,
    fontWeight: "900",
  },
  json: {
    color: "#38403C",
    fontFamily: "monospace",
    fontSize: 10,
    lineHeight: 16,
  },
});
