import { Stack, usePathname } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { StyleSheet, View } from "react-native";

import { AuthProvider } from "@/auth/auth-context";
import { BottomNav } from "@/components/bottom-nav";

const TAB_PATHS = new Set(["/", "/explore", "/recommend", "/mypage", "/mypage/saved-places"]);

export default function RootLayout() {
  const pathname = usePathname();
  return (
    <AuthProvider>
      <StatusBar style="dark" />
      <View style={styles.root}>
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: "#F7F9F8" },
            animation: "none",
          }}
        />
        {TAB_PATHS.has(pathname) ? <BottomNav /> : null}
      </View>
    </AuthProvider>
  );
}

const styles = StyleSheet.create({ root: { flex: 1 } });
