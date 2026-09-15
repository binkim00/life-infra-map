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
  report_type?: string;
  status?: string;
  description?: string;
  created_at?: string;
  admin_note?: string;
};
export default function MyReportsScreen() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("all");
  const {
    data: reports,
    loading,
    error,
    reload: load,
  } = useResource<Report[]>(
    () =>
      recommendationApi
        .myPlaceReports({ page, page_size: 20, ...(status === "all" ? {} : { status }) })
        .then((data) => (data.results || []) as Report[]),
    [],
    true,
    `${page}:${status}`,
  );
  return (
    <Screen
      title="내 장소 제보"
      subtitle="접수한 장소 정보와 검토 결과를 확인하세요."
      back
      action={
        <Pressable onPress={() => router.push("/place-report")} style={ui.button}>
          <Text style={ui.buttonText}>새 제보</Text>
        </Pressable>
      }
    >
      <View style={styles.filters}>
        {[["all", "전체"], ["pending", "대기"], ["approved", "승인"], ["rejected", "반려"]].map(([value, label]) => (
          <Pressable
            key={value}
            onPress={() => { setStatus(value); setPage(1); }}
            style={[styles.filter, status === value && styles.filterActive]}
          >
            <Text style={[styles.filterText, status === value && styles.filterTextActive]}>{label}</Text>
          </Pressable>
        ))}
      </View>
      <LoadState
        loading={loading}
        error={error}
        empty={!reports.length}
        retry={load}
      />
      <View style={styles.list}>
        {reports.map((report) => (
          <View key={report.id} style={ui.card}>
            <View style={ui.row}>
              <Text style={styles.name}>
                {report.place_name || `제보 #${report.id}`}
              </Text>
              <Text style={[styles.status, report.status === "rejected" && styles.statusRejected]}>
                {placeReportStatusLabel(report.status)}
              </Text>
            </View>
            <Text style={ui.muted}>
              {placeReportTypeLabel(report.report_type)} ·{" "}
              {report.created_at
                ? new Date(report.created_at).toLocaleDateString()
                : ""}
            </Text>
            {report.description ? (
              <Text style={styles.content}>{report.description}</Text>
            ) : null}
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/mypage/report-detail" as never,
                  params: { id: String(report.id) },
                })
              }
              style={ui.buttonSecondary}
            >
              <Text style={ui.buttonSecondaryText}>제보 상세 보기</Text>
            </Pressable>
            {report.admin_note ? (
              <Text style={ui.success}>관리자 답변: {report.admin_note}</Text>
            ) : null}
          </View>
        ))}
      </View>
      <Pagination
        page={page}
        setPage={setPage}
        hasNext={reports.length === 20}
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
  name: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { color: "#0F766E", fontSize: 11, fontWeight: "800" },
  statusRejected: { color: "#D94B4B" },
  content: { marginTop: 10, color: "#38403C", fontSize: 12, lineHeight: 19 },
});
