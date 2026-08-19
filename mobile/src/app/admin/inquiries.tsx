import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { Screen, ui } from "@/components/screen";
type Inquiry = {
  id: number;
  title: string;
  content?: string;
  status?: string;
  admin_reply?: string;
  user_nickname?: string;
  username?: string;
};
export default function AdminInquiriesScreen() {
  const [items, setItems] = useState<Inquiry[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const load = () =>
    boardsApi
      .adminInquiries()
      .then((data) => setItems(data as Inquiry[]))
      .catch(() => setError("문의 목록을 불러오지 못했습니다."));
  useEffect(() => {
    void load();
  }, []);
  const answer = async (item: Inquiry) => {
    await boardsApi.updateAdminInquiry(item.id, {
      adminReply: drafts[item.id] || "",
      status: "answered",
    });
    load();
  };
  return (
    <Screen title="문의 관리" subtitle="회원 문의 답변" back>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      <View style={styles.list}>
        {items.map((item) => (
          <View key={item.id} style={ui.card}>
            <View style={ui.row}>
              <Text style={styles.title}>{item.title}</Text>
              <Text style={styles.status}>{item.status}</Text>
            </View>
            <Text style={styles.content}>{item.content}</Text>
            <TextInput
              value={drafts[item.id] ?? item.admin_reply ?? ""}
              onChangeText={(value) =>
                setDrafts((current) => ({ ...current, [item.id]: value }))
              }
              placeholder="답변 내용"
              multiline
              style={ui.textarea}
            />
            <Pressable onPress={() => answer(item)} style={ui.button}>
              <Text style={ui.buttonText}>답변 저장</Text>
            </Pressable>
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  title: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { color: "#0F766E", fontSize: 10, fontWeight: "800" },
  content: {
    marginVertical: 12,
    color: "#38403C",
    fontSize: 12,
    lineHeight: 19,
  },
});
