import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useAuth } from "@/auth/auth-context";
import { Screen } from "@/components/screen";
const LINKS = [
  ["회원 관리", "/admin/users"],
  ["커뮤니티 신고", "/admin/reports"],
  ["장소 제보 검토", "/admin/place-reports"],
  ["문의 관리", "/admin/inquiries"],
  ["운영 현황", "/admin/operations"],
] as const;
export default function AdminScreen() {
  const { isAdmin } = useAuth();
  return (
    <Screen title="관리자" subtitle="서비스 운영 기능" back>
      {isAdmin ? (
        <View style={styles.list}>
          {LINKS.map(([label, path]) => (
            <Pressable
              key={path}
              onPress={() => router.push(path as never)}
              style={styles.link}
            >
              <Text style={styles.label}>{label}</Text>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          ))}
        </View>
      ) : (
        <Text style={styles.denied}>관리자 권한이 필요합니다.</Text>
      )}
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { overflow: "hidden", borderRadius: 16, backgroundColor: "#FFFFFF" },
  link: {
    minHeight: 58,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#E3E8E5",
  },
  label: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  chevron: { color: "#89918D", fontSize: 24 },
  denied: {
    padding: 16,
    borderRadius: 12,
    backgroundColor: "#FFF0EE",
    color: "#B42318",
  },
});
