import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { StyleSheet, View } from "react-native";

import { AuthProvider } from "@/auth/auth-context";

export default function RootLayout() {
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
