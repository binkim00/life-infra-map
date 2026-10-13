import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { router, type Href } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
type Inquiry = {
  id: number;
  title: string;
  category?: string;
  content: string;
  status?: string;
  admin_reply?: string;
  created_at?: string;
};
export default function MyInquiriesScreen() {
  const { data: items, loading, error, reload: load } = useResource<Inquiry[]>(
    () => boardsApi.myInquiries().then((data) => data as Inquiry[]), [],
  );
  return (
    <Screen
      title="내 문의"
      subtitle="답변 상태와 내용을 확인합니다."
      back
      action={
        <Pressable
          onPress={() => router.push("/inquiries/new")}
          style={ui.buttonSecondary}
        >
          <Text style={ui.buttonSecondaryText}>문의하기</Text>
        </Pressable>
      }
    >
      <LoadState loading={loading} error={error} empty={!items.length} retry={load} />
      <View style={styles.list}>
        {items.map((item) => (
          <Pressable
            key={item.id}
            accessibilityRole="button"
            accessibilityLabel={`${item.title} 문의 상세 보기`}
            onPress={() => router.push(`/inquiries/${item.id}` as Href)}
            style={({ pressed }) => [ui.card, styles.card, pressed && styles.pressed]}
          >
            <View style={ui.row}>
              <View style={[styles.icon, item.status === "answered" && styles.iconAnswered]}><Text style={styles.iconText}>{item.status === "answered" ? "✓" : "?"}</Text></View>
              <View style={ui.grow}>
                <Text style={styles.title}>{item.title}</Text>
                <Text style={ui.muted}>{({ general: "일반 문의", service_issue: "서비스 불편", bug: "오류 신고" } as Record<string, string>)[item.category || "general"] || "기타 문의"}</Text>
                <Text style={ui.muted}>{item.created_at ? new Date(item.created_at).toLocaleDateString() : ""}</Text>
              </View>
              <Text style={[styles.status, item.status === "answered" && styles.statusAnswered]}>
                {item.status === "answered" ? "답변 완료" : "접수"}
              </Text>
            </View>
            <Text style={styles.preview} numberOfLines={2}>{item.content}</Text>
            <Text style={styles.more}>문의 내용과 답변 보기  ›</Text>
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  card: { gap: 8 },
  pressed: { opacity: 0.7 },
  icon: { width: 38, height: 38, alignItems: "center", justifyContent: "center", borderRadius: 13, backgroundColor: Palette.amberSoft },
  iconAnswered: { backgroundColor: Palette.accentSoft },
  iconText: { color: Palette.accent, fontSize: 15, fontWeight: "900" },
  title: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: Radius.pill, overflow: "hidden", backgroundColor: Palette.amberSoft, color: Palette.amber, fontSize: 10, fontWeight: "900" },
  statusAnswered: { backgroundColor: Palette.accentSoft, color: Palette.accent },
  preview: { marginTop: 8, color: "#5E6964", fontSize: 12, lineHeight: 18 },
  more: { marginTop: 8, color: "#0F857A", fontSize: 11, fontWeight: "900" },
});
