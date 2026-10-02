import { router } from "expo-router";
import { useEffect } from "react";
import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { useAuth } from "@/auth/auth-context";
import { Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
import { readNotificationSettings } from "@/utils/notification-settings";
import { isNotificationVisible } from "@/utils/notification-visibility";
type Notification = {
  id: number;
  title?: string;
  message?: string;
  content?: string;
  is_read?: boolean;
  target_route?: string;
  created_at?: string;
  notification_type?: string;
};
export default function NotificationsScreen() {
  const { ready, isLoggedIn } = useAuth();
  const action = useAction();
  const { data: items, loading, error, reload: load } = useResource<Notification[]>(
    async () => {
      const [data, settings] = await Promise.all([boardsApi.notifications(), readNotificationSettings()]);
      return (data as Notification[]).filter((item) => isNotificationVisible(item.notification_type, settings));
    }, [], ready && isLoggedIn,
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
            style={[styles.notification, !item.is_read && styles.unread]}
          >
            <View style={styles.notificationIcon}><Text style={styles.notificationIconText}>{(item.title || "").includes("댓글") ? "▢" : (item.title || "").includes("좋아요") ? "♥" : "●"}</Text></View>
            <View style={ui.grow}><View style={styles.titleRow}><Text style={styles.title}>{item.title || "알림"}</Text>{!item.is_read ? <View style={styles.unreadDot} /> : null}</View><Text style={styles.content}>{item.message || item.content}</Text><Text style={ui.muted}>{item.created_at ? new Date(item.created_at).toLocaleString() : ""}</Text></View>
            <Text style={styles.chevron}>›</Text>
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  notification: { minHeight: 88, padding: 14, flexDirection: "row", alignItems: "center", gap: 11, borderWidth: 1, borderColor: Palette.border, borderRadius: Radius.medium, backgroundColor: Palette.surface },
  unread: { borderColor: "#ABD6CD", backgroundColor: "#F3FAF8" }, notificationIcon: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 14, backgroundColor: Palette.accentSoft }, notificationIconText: { color: Palette.accent, fontSize: 17, fontWeight: "900" }, titleRow: { flexDirection: "row", alignItems: "center", gap: 7 }, unreadDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Palette.coral },
  title: { marginBottom: 5, color: Palette.ink, fontSize: 13, fontWeight: "900" }, content: { marginBottom: 6, color: "#38403C", fontSize: 11.5, lineHeight: 17 }, chevron: { color: "#8A9691", fontSize: 23 },
});
