import { router, usePathname } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Palette, Shadow } from "@/constants/theme";
import { AppIcon } from "@/components/app-icon";

const ITEMS = [
  { label: "홈", ios: "house.fill", android: "home", path: "/" as const },
  { label: "검색", ios: "magnifyingglass", android: "search", path: "/explore" as const },
  { label: "추천", ios: "sparkles", android: "auto_awesome", path: "/recommend" as const },
  { label: "저장", ios: "bookmark.fill", android: "bookmark", path: "/saved" as const },
  { label: "MY", ios: "person.fill", android: "person", path: "/mypage" as const },
] as const;

export function BottomNav() {
  const pathname = usePathname();
  return (
    <View style={styles.outer} pointerEvents="box-none">
      <View style={styles.nav}>
        {ITEMS.map((item) => {
          const active =
            item.path === "/"
              ? pathname === "/"
              : item.path === "/mypage"
                ? pathname.startsWith("/mypage") && !pathname.startsWith("/mypage/saved-places")
                : item.path === "/saved"
                  ? pathname === "/saved" || pathname.startsWith("/mypage/saved-places")
                  : pathname.startsWith(item.path);
          return (
            <Pressable
              key={item.path}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={item.label}
              onPress={() => {
                if (!active) router.navigate(item.path as never);
              }}
              style={({ pressed }) => [styles.item, pressed && styles.pressed]}
            >
              <AppIcon ios={item.ios} android={item.android} size={21} color={active ? Palette.accent : "#89918D"} />
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
    height: 84,
    alignItems: "center",
    paddingHorizontal: 12,
    paddingBottom: 8,
  },
  nav: {
    width: "100%",
    maxWidth: 500,
    height: 68,
    paddingHorizontal: 6,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    borderWidth: 1,
    borderColor: "#E1E6E3",
    borderRadius: 22,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  item: {
    minWidth: 54,
    minHeight: 50,
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
  },
  label: { color: "#89918D", fontSize: 10, fontWeight: "800" },
  labelActive: { color: Palette.accent },
  pressed: { opacity: 0.58, transform: [{ scale: 0.96 }] },
});
