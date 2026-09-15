import { useState } from "react";
import { Pagination } from "@/components/pagination";
import { router } from "expo-router";
import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
import {
  placeReportStatusLabel,
  placeReportTypeLabel,
} from "@/utils/place-report-labels";
type Report = {
  id: number;
  place_name?: string;
  suggested_name?: string;
  report_type?: string;
  status?: string;
  status_label?: string;
  description?: string;
  suggested_tags?: string[];
  suggested_category?: string;
};
export default function AdminPlaceReportsScreen() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("pending");
  const {
    data: items,
    loading,
    error,
    reload: load,
  } = useResource<Report[]>(
    () =>
      recommendationApi
        .adminPlaceReports({ page, page_size: 50, ...(status === "all" ? {} : { status }) })
        .then((data) => (data.results || []) as Report[]),
    [],
    true,
    `${page}:${status}`,
  );
  return (
    <Screen
      title="장소 제보 검토"
      subtitle="승인 시 검색 데이터와 기여도에 반영됩니다."
      back
    >
      <View style={styles.filters}>
        {[["pending", "대기"], ["approved", "승인"], ["rejected", "반려"], ["all", "전체"]].map(([value, label]) => (
          <Pressable key={value} onPress={() => { setStatus(value); setPage(1); }} style={[styles.filter, status === value && styles.filterActive]}>
            <Text style={[styles.filterText, status === value && styles.filterTextActive]}>{label}</Text>
          </Pressable>
        ))}
      </View>
      <LoadState
        loading={loading}
        error={error}
        empty={!items.length}
        retry={load}
      />
      <View style={styles.list}>
        {items.map((item) => (
          <View key={item.id} style={ui.card}>
            <View style={ui.row}>
              <Text style={styles.title}>
                {item.suggested_name || item.place_name || `제보 #${item.id}`}
              </Text>
              <Text style={styles.status}>
                {placeReportStatusLabel(item.status, item.status_label)}
              </Text>
            </View>
            <Text style={ui.muted}>
              {placeReportTypeLabel(item.report_type)}
            </Text>
            {item.report_type === "new_place" && !item.suggested_category ? (
              <Text style={styles.categoryWarning}>승인 전에 카테고리를 선택해야 합니다.</Text>
            ) : null}
            <Text style={styles.description}>{item.description}</Text>
            {item.suggested_tags?.length ? (
              <Text style={ui.muted}>{item.suggested_tags.join(" · ")}</Text>
            ) : null}
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/admin/place-report-detail" as never,
                  params: { id: String(item.id) },
                })
              }
              style={item.status === "pending" ? ui.button : ui.buttonSecondary}
            >
              <Text
                style={
                  item.status === "pending"
                    ? ui.buttonText
                    : ui.buttonSecondaryText
                }
              >
                {item.status === "pending"
                  ? "상세 확인 후 승인·반려"
                  : "검토 결과 보기"}
              </Text>
            </Pressable>
          </View>
        ))}
      </View>
      <Pagination
        page={page}
        setPage={setPage}
        hasNext={items.length === 50}
        loading={loading}
      />
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  filters: { flexDirection: "row", gap: 7 },
  filter: { minHeight: 38, flex: 1, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#DFE7E3", borderRadius: 999, backgroundColor: "#FFFFFF" },
  filterActive: { borderColor: "#0F857A", backgroundColor: "#0F857A" },
  filterText: { color: "#5F6B66", fontSize: 11, fontWeight: "800" },
  filterTextActive: { color: "#FFFFFF" },
  categoryWarning: { marginTop: 8, padding: 9, borderRadius: 10, backgroundColor: "#FFF7E6", color: "#B7791F", fontSize: 11, fontWeight: "800" },
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
