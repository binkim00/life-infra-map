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
  const {
    data: reports,
    loading,
    error,
    reload: load,
  } = useResource<Report[]>(
    () =>
      recommendationApi
        .myPlaceReports({ page, page_size: 20 })
        .then((data) => (data.results || []) as Report[]),
    [],
    true,
    String(page),
  );
  return (
    <Screen title="장소 제보 내역" subtitle="등록한 장소 정보 수정 요청" back>
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
              <Text style={styles.status}>
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
  name: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { color: "#0F766E", fontSize: 11, fontWeight: "800" },
  content: { marginTop: 10, color: "#38403C", fontSize: 12, lineHeight: 19 },
});
