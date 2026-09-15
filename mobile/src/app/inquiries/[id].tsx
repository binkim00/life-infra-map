import { useLocalSearchParams } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { boardsApi } from "@/api/boards";
import { LoadState } from "@/components/load-state";
import { Screen, ui } from "@/components/screen";
import { useResource } from "@/hooks/use-resource";
import { Palette, Radius } from "@/constants/theme";

type Inquiry = {
  id: number;
  title: string;
  content: string;
  status?: string;
  admin_reply?: string;
  created_at?: string;
  answered_at?: string;
};

export default function InquiryDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data, loading, error, reload } = useResource<Inquiry | null>(
    () => boardsApi.inquiry(id).then((item) => item as Inquiry),
    null,
    Boolean(id),
    id,
  );

  return (
    <Screen title="문의 상세" subtitle="접수 내용과 관리자 답변을 확인합니다." back>
      <LoadState loading={loading} error={error} empty={!loading && !error && !data} retry={reload} />
      {data ? (
        <>
          <View style={ui.card}>
            <View style={ui.row}>
              <Text style={styles.title}>{data.title}</Text>
              <Text style={styles.status}>{data.status === "answered" ? "답변 완료" : "접수"}</Text>
            </View>
            <Text style={ui.muted}>{data.created_at ? new Date(data.created_at).toLocaleString() : "접수 시각 정보 없음"}</Text>
            <Text style={styles.content}>{data.content}</Text>
          </View>
          <Text style={ui.sectionTitle}>관리자 답변</Text>
          <View style={[ui.card, data.admin_reply ? styles.answered : styles.waiting]}>
            <View style={styles.replyHeader}><View style={[styles.timelineDot, data.admin_reply && styles.timelineDone]}><Text style={styles.timelineText}>{data.admin_reply ? "✓" : "…"}</Text></View><Text style={styles.replyTitle}>{data.admin_reply ? "답변이 등록되었습니다" : "담당자가 확인하고 있습니다"}</Text></View>
            <Text style={data.admin_reply ? styles.reply : ui.muted}>
              {data.admin_reply || "아직 답변을 준비하고 있습니다."}
            </Text>
            {data.answered_at ? <Text style={ui.muted}>{new Date(data.answered_at).toLocaleString()}</Text> : null}
          </View>
        </>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { minWidth: 0, flex: 1, color: "#17201D", fontSize: 17, fontWeight: "900" },
  status: { color: "#0F857A", fontSize: 11, fontWeight: "900" },
  content: { marginTop: 16, color: "#38403C", fontSize: 13, lineHeight: 21 },
  answered: { borderColor: "#B9DED5", backgroundColor: "#EFF8F5" },
  waiting: { borderColor: "#E0E6E3", backgroundColor: "#F7F9F8" },
  reply: { color: "#23443C", fontSize: 13, lineHeight: 21 },
  replyHeader: { marginBottom: 12, flexDirection: "row", alignItems: "center", gap: 9 },
  timelineDot: { width: 30, height: 30, alignItems: "center", justifyContent: "center", borderRadius: Radius.pill, backgroundColor: Palette.surfaceMuted },
  timelineDone: { backgroundColor: Palette.accent },
  timelineText: { color: "#FFFFFF", fontSize: 12, fontWeight: "900" },
  replyTitle: { color: Palette.ink, fontSize: 12, fontWeight: "900" },
});
