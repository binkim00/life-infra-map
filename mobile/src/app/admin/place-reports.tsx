import { useState } from "react";
import { Pagination } from "@/components/pagination";
import { router } from "expo-router";
import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
type Report = {
  id: number;
  place_name?: string;
  suggested_name?: string;
  report_type?: string;
  status?: string;
  description?: string;
  suggested_tags?: string[];
};
export default function AdminPlaceReportsScreen() {
  const [page, setPage] = useState(1);
  const { data: items, loading, error, reload: load } = useResource<Report[]>(
    () => recommendationApi.adminPlaceReports({ page, page_size: 50 }).then((data) => (data.results || []) as Report[]), [], true, String(page),
  );
  return (
    <Screen
      title="장소 제보 검토"
      subtitle="승인 시 검색 데이터와 기여도에 반영됩니다."
      back
    >
      <LoadState loading={loading} error={error} empty={!items.length} retry={load} />
      <View style={styles.list}>
        {items.map((item) => (
          <View key={item.id} style={ui.card}>
            <View style={ui.row}>
              <Text style={styles.title}>
                {item.suggested_name || item.place_name || `제보 #${item.id}`}
              </Text>
              <Text style={styles.status}>{item.status}</Text>
            </View>
            <Text style={ui.muted}>{item.report_type}</Text>
            <Text style={styles.description}>{item.description}</Text>
            {item.suggested_tags?.length ? (
              <Text style={ui.muted}>{item.suggested_tags.join(" · ")}</Text>
            ) : null}
            <Pressable onPress={() => router.push({ pathname: "/admin/place-report-detail" as never, params: { id: String(item.id) } })} style={ui.buttonSecondary}>
              <Text style={ui.buttonSecondaryText}>사진·본문 확인 및 검토</Text>
            </Pressable>
          </View>
        ))}
      </View>
      <Pagination page={page} setPage={setPage} hasNext={items.length === 50} loading={loading} />
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  title: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { color: "#0F766E", fontSize: 10, fontWeight: "800" },
  description: {
    marginVertical: 10,
    color: "#38403C",
    fontSize: 12,
    lineHeight: 19,
  },
  reject: { color: "#B42318", fontSize: 12, fontWeight: "900" },
});
