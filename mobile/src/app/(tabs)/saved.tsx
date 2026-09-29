import { Redirect } from "expo-router";
import { ActivityIndicator, View } from "react-native";

import { useAuth } from "@/auth/auth-context";
import SavedPlacesScreen from "./mypage/saved-places";

export default function SavedTabScreen() {
  const { ready, isLoggedIn } = useAuth();
  if (!ready) return <View style={{ flex: 1, justifyContent: "center" }}><ActivityIndicator /></View>;
  if (!isLoggedIn) return <Redirect href="/login" />;
  return <SavedPlacesScreen />;
}
