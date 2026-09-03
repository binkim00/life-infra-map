import { Redirect, Slot } from "expo-router";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { useAuth } from "@/auth/auth-context";

function GateLoading() {
  return (
    <View style={styles.center}>
      <ActivityIndicator color="#0F766E" />
      <Text style={styles.message}>로그인 정보를 확인하고 있습니다.</Text>
    </View>
  );
}

export function AuthRouteGate() {
  const { ready, isLoggedIn } = useAuth();

  if (!ready) return <GateLoading />;
  if (!isLoggedIn) return <Redirect href="/login" />;
  return <Slot />;
}

export function AdminRouteGate() {
  const { ready, isLoggedIn, isAdmin } = useAuth();

  if (!ready) return <GateLoading />;
  if (!isLoggedIn) return <Redirect href="/login" />;
  if (!isAdmin) return <Redirect href="/mypage" />;
  return <Slot />;
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    backgroundColor: "#F5F7F6",
  },
  message: { color: "#686159", fontSize: 12, fontWeight: "700" },
});
