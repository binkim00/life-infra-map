import { Stack, usePathname } from "expo-router";
import { useEffect } from "react";
import { StatusBar } from "expo-status-bar";
import { BackHandler, StyleSheet, View } from "react-native";
import { handleAppBack } from "@/utils/back-navigation";

import { AuthProvider } from "@/auth/auth-context";

export default function RootLayout() {
  const pathname = usePathname();
  useEffect(() => {
    const listener = BackHandler.addEventListener("hardwareBackPress", () => handleAppBack(pathname));
    return () => listener.remove();
  }, [pathname]);
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
      </View>
    </AuthProvider>
  );
}

const styles = StyleSheet.create({ root: { flex: 1 } });
