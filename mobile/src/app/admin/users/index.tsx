import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { router } from "expo-router";
import { useMemo, useState } from "react";

import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
import { tierDisplay, tierColor } from "@/utils/tier-display";
type User = {
  id: number;
  username?: string;
  nickname?: string;
  email?: string;
  role?: string;
  is_staff?: boolean;
  tier?: string;
  tier_label?: string;
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
            style={({ pressed }) => [ui.card, styles.card, pressed && styles.pressed]}
          >
            <View style={ui.row}>
              <View style={styles.avatar}><Text style={styles.avatarText}>{(user.nickname || user.username || "?").slice(0, 1).toUpperCase()}</Text></View>
              <View style={ui.grow}>
                <Text style={styles.name}>
                  {user.nickname || user.username}
                </Text>
                <Text style={ui.muted}>
                  {user.username} · {user.email || "이메일 없음"}
                </Text>
              </View>
              <Text style={[styles.role, { color: tierColor(user) }, (user.is_staff || user.role === "ADMIN" || user.role === "ROLE_ADMIN") && styles.roleAdmin]}>
                {user.is_staff || user.role === "ADMIN" || user.role === "ROLE_ADMIN"
                  ? "관리자"
                  : user.tier ? tierDisplay(user).label : "일반 회원"}
              </Text>
              <Text style={styles.chevron}>›</Text>
            </View>
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  card: { paddingVertical: 13 },
  pressed: { opacity: 0.7 },
  avatar: { width: 42, height: 42, alignItems: "center", justifyContent: "center", borderRadius: 15, backgroundColor: Palette.accentSoft },
  avatarText: { color: Palette.accent, fontSize: 15, fontWeight: "900" },
  name: { marginBottom: 5, color: "#222222", fontSize: 14, fontWeight: "900" },
  role: { paddingHorizontal: 8, paddingVertical: 5, overflow: "hidden", borderRadius: Radius.pill, backgroundColor: Palette.surfaceMuted, color: Palette.muted, fontSize: 9, fontWeight: "900" },
  roleAdmin: { backgroundColor: Palette.coralSoft, color: Palette.coral },
  chevron: { color: Palette.accent, fontSize: 21, fontWeight: "800" },
});
