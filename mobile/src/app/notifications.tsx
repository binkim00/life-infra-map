import { router } from "expo-router";
import { useEffect, useState } from "react";
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
  const [items, setItems] = useState<Notification[]>([]);
  const [error, setError] = useState("");
  const load = () =>
    boardsApi
      .notifications()
      .then((data) => setItems(data as Notification[]))
      .catch(() => setError("알림을 불러오지 못했습니다."));
  useEffect(() => {
    if (!ready) return;
    if (!isLoggedIn) {
      router.replace("/login");
      return;
    }
    void load();
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
          onPress={async () => {
            await boardsApi.readAllNotifications();
            load();
          }}
          style={ui.buttonSecondary}
        >
          <Text style={ui.buttonSecondaryText}>모두 읽음</Text>
        </Pressable>
      }
    >
      {error ? <Text style={ui.error}>{error}</Text> : null}
      <View style={styles.list}>
        {items.map((item) => (
          <Pressable
            key={item.id}
            onPress={() => open(item)}
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
