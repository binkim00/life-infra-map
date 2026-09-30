import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
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
  ["permanent_ban", "영구 이용 제한", 0],
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
  const requestPenalty = (type: string, label: string, days: number) => {
    if (!reason.trim()) {
      setStatus("제재 사유를 입력해 주세요.");
      return;
    }
    Alert.alert(
      "회원 제재 확인",
      `${label} 조치를 적용할까요? 적용 후에는 운영 기록에 남습니다.`,
      [
        { text: "취소", style: "cancel" },
        {
          text: "적용",
          style: "destructive",
          onPress: () => action.run(() => penalty(type, days)),
        },
      ],
    );
  };
  return (
    <Screen
      title={data.nickname || data.username || "회원 상세"}
      subtitle={`${data.email || ""} · 기여도 ${data.contribution ?? data.contribution_score ?? 0}`}
      back
    >
      <LoadState loading={loading} error={error} retry={load} />
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      {status ? (
        <Text style={status.includes("입력") ? ui.error : ui.success}>{status}</Text>
      ) : null}
      {data.id ? (
        <View style={styles.summary}>
          <View><Text style={styles.summaryNumber}>{data.posts?.length || 0}</Text><Text style={ui.muted}>게시글</Text></View>
          <View><Text style={styles.summaryNumber}>{data.comments?.length || 0}</Text><Text style={ui.muted}>댓글</Text></View>
          <View><Text style={styles.summaryNumber}>{data.penalties?.length || 0}</Text><Text style={ui.muted}>제재 이력</Text></View>
        </View>
      ) : null}
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
              onPress={() => requestPenalty(type, label, days)}
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
        <Pressable
          disabled={action.busy || loading || Boolean(error) || !message.trim()}
          onPress={() => action.run(notify)}
          style={[ui.button, styles.actions, !message.trim() && styles.disabled]}
        >
          <Text style={ui.buttonText}>{action.busy ? "보내는 중…" : "알림 보내기"}</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  actions: { marginTop: 10, flexWrap: "wrap" },
  danger: { color: "#B42318", fontSize: 12, fontWeight: "900" },
  summary: { padding: 18, flexDirection: "row", justifyContent: "space-around", borderRadius: 18, backgroundColor: "#E9F5F2" },
  summaryNumber: { marginBottom: 3, color: "#0F857A", fontSize: 22, fontWeight: "900", textAlign: "center" },
  disabled: { opacity: 0.45 },
});
