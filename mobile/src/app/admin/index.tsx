import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useAuth } from "@/auth/auth-context";
import { Screen } from "@/components/screen";
import { recommendationApi } from "@/api/recommendations";
import { LoadState } from "@/components/load-state";
import { useResource } from "@/hooks/use-resource";
import { Palette, Radius } from "@/constants/theme";
import { AppIcon } from "@/components/app-icon";
const LINKS = [
  ["수집 근거 검토", "확인 필요한 근거를 판정합니다.", "doc.text.magnifyingglass", "fact_check", "/admin/evidence"],
  ["수집 판정 기록", "수집 실행과 저장 결과를 확인합니다.", "clock.arrow.circlepath", "history", "/admin/research-audits"],
  ["회원 관리", "회원 정보와 제재를 관리합니다.", "person.2.fill", "group", "/admin/users"],
  ["커뮤니티 신고", "게시글과 댓글 신고를 처리합니다.", "flag.fill", "flag", "/admin/reports"],
  ["장소 제보 검토", "사용자가 보낸 장소 정보를 검토합니다.", "mappin.and.ellipse", "add_location_alt", "/admin/place-reports"],
  ["문의 관리", "회원 문의를 확인하고 답변합니다.", "bubble.left.and.bubble.right.fill", "forum", "/admin/inquiries"],
  ["운영 현황", "수집과 검색 데이터 상태를 확인합니다.", "chart.bar.fill", "bar_chart", "/admin/operations"],
] as const;
export default function AdminScreen() {
  const { isAdmin } = useAuth();
  const { data, loading, error, reload } = useResource(
    () => recommendationApi.adminOperations({ days: 1 }) as Promise<{
      generated_at?: string;
      period?: { new_evidence?: number; new_place_tags?: number };
      queue?: { queued?: number; processing?: number; retry?: number; failed?: number };
    }>,
    {},
    isAdmin,
  );
  const pending = (data.queue?.queued || 0) + (data.queue?.retry || 0);
  return (
    <Screen title="운영 센터" subtitle="여기일지도를 안전하고 건강하게 관리합니다." back>
      {isAdmin ? (
        <View style={styles.content}>
          <LoadState loading={loading} error={error} retry={reload} />
          {!loading && !error && data.generated_at ? (
            <View style={styles.summary}>
              <View style={styles.summaryHeader}>
                <View>
                  <Text style={styles.summaryEyebrow}>지금 처리할 일</Text>
                  <Text style={styles.summaryNumber}>{pending.toLocaleString()}건</Text>
                </View>
                <Pressable accessibilityRole="button" onPress={reload} style={styles.refresh}>
                  <Text style={styles.refreshText}>새로고침</Text>
                </Pressable>
              </View>
              <View style={styles.metrics}>
                <View style={styles.metric}><Text style={styles.metricNumber}>{data.period?.new_evidence?.toLocaleString() ?? "—"}</Text><Text style={styles.metricLabel}>오늘 신규 근거</Text></View>
                <View style={styles.metric}><Text style={styles.metricNumber}>{data.period?.new_place_tags?.toLocaleString() ?? "—"}</Text><Text style={styles.metricLabel}>오늘 신규 태그</Text></View>
                <View style={styles.metric}><Text style={styles.metricNumber}>{data.queue?.processing?.toLocaleString() ?? "—"}</Text><Text style={styles.metricLabel}>처리 중</Text></View>
                <View style={[styles.metric, (data.queue?.failed || 0) > 0 && styles.metricDanger]}><Text style={styles.metricNumber}>{data.queue?.failed?.toLocaleString() ?? "—"}</Text><Text style={styles.metricLabel}>수집 실패</Text></View>
              </View>
              <Text style={styles.updated}>마지막 갱신 {new Date(data.generated_at).toLocaleString()}</Text>
            </View>
          ) : null}
          <Text style={styles.sectionTitle}>관리 메뉴</Text>
          <View style={styles.list}>
          {LINKS.map(([label, description, ios, android, path]) => (
            <Pressable
              key={path}
              onPress={() => router.push(path as never)}
              style={({ pressed }) => [styles.link, pressed && styles.pressed]}
            >
              <View style={styles.symbol}><AppIcon ios={ios} android={android} size={20} color={Palette.accent} /></View>
              <View style={styles.copy}>
                <Text style={styles.label}>{label}</Text>
                <Text style={styles.description}>{description}</Text>
              </View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          ))}
          </View>
        </View>
      ) : (
        <Text style={styles.denied}>관리자 권한이 필요합니다.</Text>
      )}
    </Screen>
  );
}
const styles = StyleSheet.create({
  content: { gap: 16 },
  summary: { padding: 18, gap: 16, borderRadius: Radius.large, backgroundColor: "#123D38" },
  summaryHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  summaryEyebrow: { color: "#BDE6DF", fontSize: 12, fontWeight: "800" },
  summaryNumber: { marginTop: 3, color: "#FFFFFF", fontSize: 30, fontWeight: "900" },
  refresh: { minHeight: 38, paddingHorizontal: 13, alignItems: "center", justifyContent: "center", borderRadius: Radius.pill, backgroundColor: "rgba(255,255,255,0.12)" },
  refreshText: { color: "#FFFFFF", fontSize: 11, fontWeight: "800" },
  metrics: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  metric: { width: "47%", flexGrow: 1, padding: 12, borderRadius: Radius.small, backgroundColor: "rgba(255,255,255,0.1)" },
  metricDanger: { backgroundColor: "rgba(255,118,94,0.22)" },
  metricNumber: { color: "#FFFFFF", fontSize: 20, fontWeight: "900" },
  metricLabel: { marginTop: 3, color: "#CDE4E0", fontSize: 10 },
  updated: { color: "#B7D3CE", fontSize: 10 },
  sectionTitle: { color: Palette.ink, fontSize: 18, fontWeight: "900" },
  list: { overflow: "hidden", borderWidth: 1, borderColor: Palette.border, borderRadius: Radius.medium, backgroundColor: "#FFFFFF" },
  link: {
    minHeight: 72,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#E3E8E5",
  },
  symbol: { width: 38, height: 38, alignItems: "center", justifyContent: "center", borderRadius: 13, backgroundColor: Palette.accentSoft },
  copy: { minWidth: 0, flex: 1 },
  label: { color: Palette.ink, fontSize: 14, fontWeight: "900" },
  description: { marginTop: 4, color: Palette.muted, fontSize: 10 },
  chevron: { color: "#89918D", fontSize: 24 },
  pressed: { opacity: 0.58 },
  denied: {
    padding: 16,
    borderRadius: 12,
    backgroundColor: "#FFF0EE",
    color: "#B42318",
  },
});
