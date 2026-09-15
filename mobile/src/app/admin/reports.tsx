import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
type Report = {
  id: number;
  report_type?: string;
  reason?: string;
  status?: string;
  reporter_nickname?: string;
  target_type?: string;
  created_at?: string;
};
export default function AdminReportsScreen() {
  const action = useAction();
  const [notes, setNotes] = useState<Record<number, string>>({});
  const { data: items, loading, error, reload: load } = useResource<Report[]>(
    () => boardsApi.reports().then((data) => data as Report[]), [],
  );
  const process = async (item: Report, status: string) => {
    await boardsApi.processReport(item.id, {
      status,
      adminMemo: notes[item.id] || "",
    });
    load();
  };
  return (
    <Screen title="커뮤니티 신고" subtitle="게시글과 댓글 신고 처리" back>
      <LoadState loading={loading} error={error} empty={!items.length} retry={load} />
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      <View style={styles.list}>
        {items.map((item) => (
          <View key={item.id} style={[ui.card, styles.card]}>
            <View style={ui.row}>
              <View style={styles.icon}><Text style={styles.iconText}>!</Text></View>
              <Text style={styles.title}>
                신고 #{item.id} · {item.target_type === "post" ? "게시글" : item.target_type === "comment" ? "댓글" : "콘텐츠"}
              </Text>
              <Text style={[styles.status, item.status === "penalized" && styles.statusDone]}>{({ pending: "대기", passed: "기각", penalized: "조치 완료" } as Record<string, string>)[item.status || ""] || "확인 필요"}</Text>
            </View>
            <Text style={styles.reason}>{item.reason}</Text>
            <TextInput
              value={notes[item.id] || ""}
              onChangeText={(value) =>
                setNotes((current) => ({ ...current, [item.id]: value }))
              }
              placeholder="처리 메모"
              placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
              style={ui.input}
            />
            <View style={ui.row}>
              <Pressable
                disabled={action.busy}
                onPress={() => action.run(() => process(item, "passed"))}
                style={ui.buttonSecondary}
              >
                <Text style={ui.buttonSecondaryText}>신고 기각</Text>
              </Pressable>
              <Pressable
                disabled={action.busy}
                onPress={() => action.run(() => process(item, "penalized"))}
                style={ui.buttonSecondary}
              >
                <Text style={styles.actionText}>작성자 조치 완료</Text>
              </Pressable>
            </View>
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  card: { gap: 5 },
  icon: { width: 34, height: 34, alignItems: "center", justifyContent: "center", borderRadius: 11, backgroundColor: Palette.dangerSoft },
  iconText: { color: Palette.danger, fontSize: 15, fontWeight: "900" },
  title: { flex: 1, color: "#222222", fontSize: 13, fontWeight: "900" },
  status: { paddingHorizontal: 8, paddingVertical: 5, overflow: "hidden", borderRadius: Radius.pill, backgroundColor: Palette.amberSoft, color: Palette.amber, fontSize: 10, fontWeight: "900" },
  statusDone: { backgroundColor: Palette.successSoft, color: Palette.success },
  reason: { marginVertical: 10, color: "#38403C", fontSize: 12 },
  actionText: { color: "#D94B4B", fontSize: 12, fontWeight: "900" },
  delete: { color: "#B42318", fontSize: 12, fontWeight: "900" },
});
