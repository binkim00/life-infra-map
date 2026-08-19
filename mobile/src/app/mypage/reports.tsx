import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
type Report = {
  id: number;
  place_name?: string;
  report_type?: string;
  status?: string;
  content?: string;
  created_at?: string;
  admin_note?: string;
};
export default function MyReportsScreen() {
  const [reports, setReports] = useState<Report[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    recommendationApi
      .myPlaceReports({ page: 1, page_size: 50 })
      .then((data) => setReports((data.results || []) as Report[]))
      .catch(() => setError("제보 내역을 불러오지 못했습니다."));
  }, []);
  return (
    <Screen title="장소 제보 내역" subtitle="등록한 장소 정보 수정 요청" back>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      <View style={styles.list}>
        {reports.map((report) => (
          <View key={report.id} style={ui.card}>
            <View style={ui.row}>
              <Text style={styles.name}>
                {report.place_name || `제보 #${report.id}`}
              </Text>
              <Text style={styles.status}>{report.status || "접수"}</Text>
            </View>
            <Text style={ui.muted}>
              {report.report_type} ·{" "}
              {report.created_at
                ? new Date(report.created_at).toLocaleDateString()
                : ""}
            </Text>
            {report.content ? (
              <Text style={styles.content}>{report.content}</Text>
            ) : null}
            {report.admin_note ? (
              <Text style={ui.success}>관리자 답변: {report.admin_note}</Text>
            ) : null}
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  name: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { color: "#0F766E", fontSize: 11, fontWeight: "800" },
  content: { marginTop: 10, color: "#38403C", fontSize: 12, lineHeight: 19 },
});
