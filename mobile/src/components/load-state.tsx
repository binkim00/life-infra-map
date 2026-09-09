import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { ui } from "./screen";

export function LoadState({
  loading,
  error,
  empty,
  retry,
  emptyText = "등록된 내역이 없습니다.",
}: {
  loading: boolean;
  error?: string;
  empty?: boolean;
  retry: () => void;
  emptyText?: string;
}) {
  if (loading)
    return (
      <View style={ui.card}>
        <ActivityIndicator color="#0F766E" />
        <Text style={ui.muted}>불러오는 중입니다.</Text>
      </View>
    );
  if (error)
    return (
      <View style={ui.card}>
        <Text style={ui.error}>{error}</Text>
        <Pressable onPress={retry} style={ui.buttonSecondary}>
          <Text style={ui.buttonSecondaryText}>다시 시도</Text>
        </Pressable>
      </View>
    );
  if (empty) return <Text style={ui.muted}>{emptyText}</Text>;
  return null;
}
