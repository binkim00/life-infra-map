import { useState } from "react";
import { Pagination } from "@/components/pagination";
import { router } from "expo-router";
import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";

import { Pressable, StyleSheet, Text, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
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
          <Pressable
            key={report.id}
            accessibilityRole="button"
            accessibilityLabel={`${report.place_name || `제보 ${report.id}`} 상세 보기`}
            onPress={() => router.push({ pathname: "/mypage/report-detail" as never, params: { id: String(report.id) } })}
            style={({ pressed }) => [ui.card, styles.report, pressed && styles.pressed]}
          >
            <View style={ui.row}>
              <View style={styles.reportIcon}><Text style={styles.reportIconText}>⌖</Text></View>
              <View style={ui.grow}>
                <Text style={styles.receipt}>제보 #{report.id}</Text>
                <Text style={styles.name}>{report.place_name || "장소 이름 확인 중"}</Text>
              </View>
              <Text style={[styles.status, report.status === "approved" && styles.statusApproved, report.status === "rejected" && styles.statusRejected]}>
                {placeReportStatusLabel(report.status)}
              </Text>
            </View>
            <Text style={styles.meta}>
              {placeReportTypeLabel(report.report_type)} ·{" "}
              {report.created_at
                ? new Date(report.created_at).toLocaleDateString()
                : ""}
            </Text>
            {report.description ? (
              <Text style={styles.content}>{report.description}</Text>
            ) : null}
            {report.admin_note ? (
              <View style={styles.adminNote}><Text style={styles.adminNoteLabel}>검토 메모</Text><Text style={styles.adminNoteText}>{report.admin_note}</Text></View>
            ) : null}
            <Text style={styles.more}>접수 내용과 처리 과정 보기  ›</Text>
          </Pressable>
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
  report: { gap: 10 },
  pressed: { opacity: 0.7, transform: [{ scale: 0.99 }] },
  filters: { flexDirection: "row", gap: 7 },
  filter: { minHeight: 38, flex: 1, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#DFE7E3", borderRadius: 999, backgroundColor: "#FFFFFF" },
  filterActive: { borderColor: "#0F857A", backgroundColor: "#0F857A" },
  filterText: { color: "#5F6B66", fontSize: 11, fontWeight: "800" },
  filterTextActive: { color: "#FFFFFF" },
  reportIcon: { width: 42, height: 42, alignItems: "center", justifyContent: "center", borderRadius: 14, backgroundColor: Palette.accentSoft },
  reportIconText: { color: Palette.accent, fontSize: 21, fontWeight: "900" },
  receipt: { marginBottom: 2, color: Palette.muted, fontSize: 10, fontWeight: "700" },
  name: { color: Palette.ink, fontSize: 15, fontWeight: "900" },
  status: { paddingHorizontal: 9, paddingVertical: 6, borderRadius: Radius.pill, overflow: "hidden", backgroundColor: Palette.amberSoft, color: Palette.amber, fontSize: 10, fontWeight: "900" },
  statusApproved: { backgroundColor: Palette.successSoft, color: Palette.success },
  statusRejected: { backgroundColor: Palette.dangerSoft, color: Palette.danger },
  meta: { color: Palette.muted, fontSize: 11 },
  content: { marginTop: 10, color: "#38403C", fontSize: 12, lineHeight: 19 },
  adminNote: { padding: 12, borderRadius: Radius.small, backgroundColor: Palette.surfaceMuted },
  adminNoteLabel: { marginBottom: 4, color: Palette.ink, fontSize: 10, fontWeight: "900" },
  adminNoteText: { color: Palette.muted, fontSize: 11, lineHeight: 17 },
  more: { color: Palette.accent, fontSize: 11, fontWeight: "900" },
});
