import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
type Inquiry = {
  id: number;
  title: string;
  category?: string;
  content?: string;
  status?: string;
  admin_reply?: string;
  user_nickname?: string;
  username?: string;
};
export default function AdminInquiriesScreen() {
  const action = useAction();
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const { data: items, loading, error, reload: load } = useResource<Inquiry[]>(
    () => boardsApi.adminInquiries().then((data) => data as Inquiry[]), [],
  );
  const answer = async (item: Inquiry) => {
    const reply = (drafts[item.id] ?? item.admin_reply ?? "").trim();
    if (!reply) throw new Error("답변 내용을 입력해 주세요.");
    await boardsApi.updateAdminInquiry(item.id, {
      adminReply: reply,
      status: "answered",
    });
    load();
  };
  return (
    <Screen title="문의 관리" subtitle="회원 문의 답변" back>
      <LoadState loading={loading} error={error} empty={!items.length} retry={load} />
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      <View style={styles.list}>
        {items.map((item) => (
          <View key={item.id} style={[ui.card, styles.card]}>
            <View style={ui.row}>
              <View style={styles.icon}><Text style={styles.iconText}>?</Text></View>
              <Text style={styles.title}>{item.title}</Text>
                <Text style={[styles.status, item.status === "answered" && styles.statusAnswered]}>{({ pending: "접수", answered: "답변 완료", closed: "종료" } as Record<string, string>)[item.status || ""] || "확인 필요"}</Text>
            </View>
            <Text style={styles.content}>{item.content}</Text>
            <Text style={ui.muted}>유형: {({ general: "일반 문의", service_issue: "서비스 불편", bug: "오류 신고" } as Record<string, string>)[item.category || "general"] || "분류 확인 필요"}</Text>
            <TextInput
              value={drafts[item.id] ?? item.admin_reply ?? ""}
              onChangeText={(value) =>
                setDrafts((current) => ({ ...current, [item.id]: value }))
              }
              placeholder="답변 내용"
              placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
              multiline
              style={ui.textarea}
            />
            <Pressable disabled={action.busy || !(drafts[item.id] ?? item.admin_reply ?? "").trim()} onPress={() => action.run(() => answer(item))} style={[ui.button, (action.busy || !(drafts[item.id] ?? item.admin_reply ?? "").trim()) && styles.disabled]}>
              <Text style={ui.buttonText}>{action.busy ? "답변 등록 중…" : "답변 등록"}</Text>
            </Pressable>
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  card: { gap: 5 },
  icon: { width: 34, height: 34, alignItems: "center", justifyContent: "center", borderRadius: 11, backgroundColor: Palette.accentSoft },
  iconText: { color: Palette.accent, fontSize: 14, fontWeight: "900" },
  title: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { paddingHorizontal: 8, paddingVertical: 5, overflow: "hidden", borderRadius: Radius.pill, backgroundColor: Palette.amberSoft, color: Palette.amber, fontSize: 10, fontWeight: "900" },
  statusAnswered: { backgroundColor: Palette.successSoft, color: Palette.success },
  content: {
    marginVertical: 12,
    color: "#38403C",
    fontSize: 12,
    lineHeight: 19,
  },
  disabled: { opacity: 0.45 },
});
