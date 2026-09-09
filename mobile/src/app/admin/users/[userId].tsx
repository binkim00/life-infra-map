import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
type UserData = {
  id?: number;
  username?: string;
  nickname?: string;
  email?: string;
  role?: string;
  contribution?: number;
  contribution_score?: number;
  penalties?: unknown[];
  posts?: unknown[];
  comments?: unknown[];
};
type AdminUserPayload = UserData & {
  user?: UserData;
  posts?: unknown[];
  comments?: unknown[];
  penalties?: unknown[];
};
const penaltyOptions = [
  ["warning", "경고", 0],
  ["suspend_3_days", "3일 정지", 3],
  ["suspend_7_days", "7일 정지", 7],
  ["suspend_30_days", "30일 정지", 30],
  ["suspend_1_year", "1년 정지", 365],
  ["permanent_ban", "영구밴", 0],
] as const;
export default function AdminUserDetailScreen() {
  const action = useAction();
  const { userId = "" } = useLocalSearchParams<{ userId: string }>();
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState("");
  const { data, loading, error, reload: load } = useResource<UserData>(
    () => boardsApi.adminUser(userId).then(result => {
      const payload = result as AdminUserPayload;
      return { ...(payload.user || payload), posts: payload.posts || [], comments: payload.comments || [], penalties: payload.penalties || [] };
    }), {}, true, userId,
  );
  const penalty = async (type: string, days: number) => {
    if (!reason.trim()) {
      setStatus("제재 사유를 입력해주세요.");
      return;
    }
    await boardsApi.createPenalty(userId, {
      penaltyType: type,
      reason: reason.trim(),
      days,
    });
    setReason("");
    setStatus("제재를 적용했습니다.");
    load();
  };
  const notify = async () => {
    if (!message.trim()) return;
    await boardsApi.notifyUser(userId, { title: "관리자 메시지", message });
    setMessage("");
    setStatus("메시지를 보냈습니다.");
  };
  return (
    <Screen
      title={data.nickname || data.username || "회원 상세"}
      subtitle={`${data.email || ""} · 기여도 ${data.contribution ?? data.contribution_score ?? 0}`}
      back
    >
      <LoadState loading={loading} error={error} retry={load} />
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      {status ? <Text style={ui.success}>{status}</Text> : null}
      <View style={ui.card}>
        <Text style={ui.label}>제재 사유</Text>
        <TextInput
          value={reason}
          onChangeText={setReason}
          placeholder="사유"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={ui.input}
        />
        <View style={[ui.row, styles.actions]}>
          {penaltyOptions.map(([type, label, days]) => (
            <Pressable
              key={type}
              disabled={action.busy || loading || Boolean(error)}
              onPress={() => action.run(() => penalty(type, days))}
              style={ui.buttonSecondary}
            >
              <Text
                style={
                  type === "permanent_ban"
                    ? styles.danger
                    : ui.buttonSecondaryText
                }
              >
                {label}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>
      <View style={ui.card}>
        <Text style={ui.label}>관리자 메시지</Text>
        <TextInput
          value={message}
          onChangeText={setMessage}
          placeholder="회원에게 보낼 메시지"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          multiline
          style={ui.textarea}
        />
        <Pressable disabled={action.busy || loading || Boolean(error)} onPress={() => action.run(notify)} style={[ui.button, styles.actions]}>
          <Text style={ui.buttonText}>메시지 보내기</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  actions: { marginTop: 10, flexWrap: "wrap" },
  danger: { color: "#B42318", fontSize: 12, fontWeight: "900" },
});
