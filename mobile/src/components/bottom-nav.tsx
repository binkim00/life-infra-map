import { router, usePathname } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Palette, Shadow } from "@/constants/theme";

const ITEMS = [
  { label: "홈", symbol: "⌂", path: "/" as const },
  { label: "검색", symbol: "⌕", path: "/explore" as const },
  { label: "추천", symbol: "✦", path: "/recommend" as const },
  { label: "저장", symbol: "▱", path: "/mypage/saved-places" as const },
  { label: "MY", symbol: "○", path: "/mypage" as const },
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
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={item.label}
              onPress={() => router.push(item.path as never)}
              style={({ pressed }) => [styles.item, pressed && styles.pressed]}
            >
              <Text style={[styles.symbol, active && styles.symbolActive]}>{item.symbol}</Text>
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
    bottom: 12,
    alignItems: "center",
    paddingHorizontal: 18,
  },
  nav: {
    width: "100%",
    maxWidth: 520,
    height: 72,
    paddingHorizontal: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    borderWidth: 1,
    borderColor: "#E1E6E3",
    borderRadius: 26,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  item: {
    minWidth: 56,
    minHeight: 54,
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
  },
  symbol: { color: "#89918D", fontSize: 22, lineHeight: 25, fontWeight: "800" },
  symbolActive: { color: Palette.accent },
  label: { color: "#89918D", fontSize: 10, fontWeight: "800" },
  labelActive: { color: Palette.accent },
  pressed: { opacity: 0.58, transform: [{ scale: 0.96 }] },
});
