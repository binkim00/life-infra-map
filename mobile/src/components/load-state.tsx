import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { Palette, Radius } from "@/constants/theme";
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
      <View accessibilityLiveRegion="polite" style={styles.stateCard}>
        <ActivityIndicator color={Palette.accent} size="small" />
        <View style={styles.copy}>
          <Text style={styles.title}>정보를 불러오고 있어요</Text>
          <Text style={ui.muted}>잠시만 기다려 주세요.</Text>
        </View>
      </View>
    );
  if (error)
    return (
      <View accessibilityLiveRegion="assertive" style={[styles.stateCard, styles.errorCard]}>
        <View style={styles.stateIcon}><Text style={styles.errorIconText}>!</Text></View>
        <View style={styles.copy}>
          <Text style={styles.title}>정보를 불러오지 못했어요</Text>
          <Text style={styles.description}>{error}</Text>
        </View>
        <Pressable accessibilityRole="button" onPress={retry} style={ui.buttonSecondary}>
          <Text style={ui.buttonSecondaryText}>다시 시도</Text>
        </Pressable>
      </View>
    );
  if (empty)
    return (
      <View style={styles.emptyCard}>
        <Text style={styles.emptySymbol}>⌁</Text>
        <Text style={styles.title}>{emptyText}</Text>
        <Text style={ui.muted}>새로운 내용이 생기면 여기에 표시됩니다.</Text>
      </View>
    );
  return null;
}

const styles = StyleSheet.create({
  stateCard: {
    minHeight: 86,
    padding: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: Palette.border,
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
  },
  errorCard: { alignItems: "flex-start", borderColor: "#F4CACA", backgroundColor: "#FFFBFB" },
  stateIcon: { width: 28, height: 28, alignItems: "center", justifyContent: "center", borderRadius: 14, backgroundColor: Palette.dangerSoft },
  errorIconText: { color: Palette.danger, fontWeight: "900" },
  copy: { minWidth: 0, flex: 1, gap: 3 },
  title: { color: Palette.ink, fontSize: 14, fontWeight: "900" },
  description: { color: Palette.danger, fontSize: 12, lineHeight: 18 },
  emptyCard: { minHeight: 132, padding: 24, alignItems: "center", justifyContent: "center", gap: 7, borderWidth: 1, borderStyle: "dashed", borderColor: Palette.border, borderRadius: Radius.medium, backgroundColor: Palette.surface },
  emptySymbol: { color: Palette.accent, fontSize: 30, fontWeight: "800" },
});
