import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { router } from "expo-router";
import { useMemo, useState } from "react";

import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
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
  const [query, setQuery] = useState("");
  const { data: users, loading, error, reload: load } = useResource<User[]>(
    () => boardsApi.adminUsers().then((data) => data as User[]), [],
  );
  const visibleUsers = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return users;
    return users.filter((user) =>
      `${user.username || ""} ${user.nickname || ""} ${user.email || ""}`
        .toLowerCase()
        .includes(keyword),
    );
  }, [query, users]);
  return (
    <Screen title="회원 관리" subtitle={`${users.length}명`} back>
      <TextInput
        value={query}
        onChangeText={setQuery}
        placeholder="아이디, 닉네임, 이메일 검색"
        placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
        style={ui.input}
      />
      <LoadState loading={loading} error={error} empty={!users.length} retry={load} />
      <View style={styles.list}>
        {!loading && !error && users.length > 0 && visibleUsers.length === 0 ? (
          <Text style={ui.muted}>검색 결과가 없습니다.</Text>
        ) : null}
        {visibleUsers.map((user) => (
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
