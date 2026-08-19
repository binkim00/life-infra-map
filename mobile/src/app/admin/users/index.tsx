import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { Screen, ui } from "@/components/screen";
type User = {
  id: number;
  username?: string;
  nickname?: string;
  email?: string;
  role?: string;
  tier?: string;
  contribution?: number;
  contribution_score?: number;
  is_active?: boolean;
};
export default function AdminUsersScreen() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    boardsApi
      .adminUsers()
      .then((data) => setUsers(data as User[]))
      .catch(() => setError("회원 목록을 불러오지 못했습니다."));
  }, []);
  return (
    <Screen title="회원 관리" subtitle={`${users.length}명`} back>
      {error ? <Text style={ui.error}>{error}</Text> : null}
      <View style={styles.list}>
        {users.map((user) => (
          <Pressable
            key={user.id}
            onPress={() => router.push(`/admin/users/${user.id}` as never)}
            style={ui.card}
          >
            <View style={ui.row}>
              <View style={ui.grow}>
                <Text style={styles.name}>
                  {user.nickname || user.username}
                </Text>
                <Text style={ui.muted}>
                  {user.username} · {user.email || "이메일 없음"}
                </Text>
              </View>
              <Text style={styles.role}>
                {user.role || user.tier || "USER"}
              </Text>
            </View>
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  name: { marginBottom: 5, color: "#222222", fontSize: 14, fontWeight: "900" },
  role: { color: "#0F766E", fontSize: 10, fontWeight: "900" },
});
