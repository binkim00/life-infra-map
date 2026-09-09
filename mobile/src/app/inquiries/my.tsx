import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { Screen, ui } from "@/components/screen";
type Inquiry = {
  id: number;
  title: string;
  content: string;
  status?: string;
  admin_reply?: string;
  created_at?: string;
};
export default function MyInquiriesScreen() {
  const [open, setOpen] = useState<number | null>(null);
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
            onPress={() => setOpen(open === item.id ? null : item.id)}
            style={ui.card}
          >
            <View style={ui.row}>
              <Text style={styles.title}>{item.title}</Text>
              <Text style={styles.status}>
                {item.status === "answered" ? "답변 완료" : "접수"}
              </Text>
            </View>
            <Text style={ui.muted}>
              {item.created_at
                ? new Date(item.created_at).toLocaleDateString()
                : ""}
            </Text>
            {open === item.id ? (
              <View style={styles.detail}>
                <Text style={styles.content}>{item.content}</Text>
                {item.admin_reply ? (
                  <Text style={ui.success}>답변: {item.admin_reply}</Text>
                ) : (
                  <Text style={ui.muted}>아직 등록된 답변이 없습니다.</Text>
                )}
              </View>
            ) : null}
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  title: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { color: "#0F766E", fontSize: 10, fontWeight: "800" },
  detail: { marginTop: 14, gap: 10 },
  content: { color: "#38403C", fontSize: 12, lineHeight: 19 },
});
