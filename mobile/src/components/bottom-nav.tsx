import { router, usePathname } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Palette, Shadow } from "@/constants/theme";

const ITEMS = [
  { label: "홈", path: "/" as const },
  { label: "일반검색", path: "/explore" as const },
  { label: "게시판", path: "/boards/free" as const },
  { label: "MY", path: "/mypage" as const },
];

export function BottomNav() {
  const pathname = usePathname();
  return (
    <View style={styles.outer} pointerEvents="box-none">
      <View style={styles.nav}>
        {ITEMS.map((item) => {
          const active =
            item.path === "/"
              ? pathname === "/"
              : pathname.startsWith(item.path);
          return (
            <Pressable
              key={item.path}
              onPress={() => router.push(item.path as never)}
              style={styles.item}
            >
              <View style={[styles.dot, active && styles.dotActive]} />
              <Text style={[styles.label, active && styles.labelActive]}>
                {item.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  outer: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 18,
    alignItems: "center",
    paddingHorizontal: 18,
  },
  nav: {
    width: "100%",
    maxWidth: 520,
    height: 66,
    paddingHorizontal: 18,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    borderWidth: 1,
    borderColor: "#E1E6E3",
    borderRadius: 24,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  item: {
    minWidth: 52,
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  dot: { width: 4, height: 4, borderRadius: 2, backgroundColor: "transparent" },
  dotActive: { backgroundColor: Palette.accent },
  label: { color: "#89918D", fontSize: 11, fontWeight: "800" },
  labelActive: { color: Palette.ink },
});
