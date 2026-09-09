import { router } from "expo-router";
import { useEffect } from "react";
import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { useAuth } from "@/auth/auth-context";
import { Screen, ui } from "@/components/screen";
type Notification = {
  id: number;
  title?: string;
  message?: string;
  content?: string;
  is_read?: boolean;
  target_route?: string;
  created_at?: string;
};
export default function NotificationsScreen() {
  const { ready, isLoggedIn } = useAuth();
  const action = useAction();
  const { data: items, loading, error, reload: load } = useResource<Notification[]>(
    () => boardsApi.notifications().then(data => data as Notification[]), [], ready && isLoggedIn,
  );
  useEffect(() => {
    if (!ready) return;
    if (!isLoggedIn) {
      router.replace("/login");
      return;
    }
  }, [isLoggedIn, ready]);
  const open = async (item: Notification) => {
    if (!item.is_read) await boardsApi.readNotification(item.id);
    if (item.target_route) router.push(item.target_route as never);
    else load();
  };
  return (
    <Screen
      title="알림"
      subtitle="서비스 활동과 관리자 메시지"
      back
      action={
        <Pressable
          disabled={action.busy || loading}
          onPress={() => action.run(async () => {
            await boardsApi.readAllNotifications();
            load();
          })}
          style={ui.buttonSecondary}
        >
          <Text style={ui.buttonSecondaryText}>모두 읽음</Text>
        </Pressable>
      }
    >
      <LoadState loading={loading} error={error} empty={!items.length} retry={load} />
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      <View style={styles.list}>
        {items.map((item) => (
          <Pressable
            key={item.id}
            disabled={action.busy}
            onPress={() => action.run(() => open(item))}
            style={[ui.card, !item.is_read && styles.unread]}
          >
            <Text style={styles.title}>{item.title || "알림"}</Text>
            <Text style={styles.content}>{item.message || item.content}</Text>
            <Text style={ui.muted}>
              {item.created_at
                ? new Date(item.created_at).toLocaleString()
                : ""}
            </Text>
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  unread: { borderColor: "#0F766E", backgroundColor: "#F3FAF8" },
  title: { marginBottom: 7, color: "#222222", fontSize: 13, fontWeight: "900" },
  content: { marginBottom: 8, color: "#38403C", fontSize: 12, lineHeight: 18 },
});
