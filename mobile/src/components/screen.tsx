import { router } from "expo-router";
import { PropsWithChildren, ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Palette, Radius, Spacing } from "@/constants/theme";

export function Screen({
  title,
  subtitle,
  children,
  back = false,
  action,
}: PropsWithChildren<{
  title: string;
  subtitle?: string;
  back?: boolean;
  action?: ReactNode;
}>) {
  return (
    <View style={styles.screen}>
      <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.header}>
            <View style={styles.headingRow}>
              {back ? (
                <Pressable onPress={() => router.back()} style={styles.back}>
                  <Text style={styles.backText}>‹</Text>
                </Pressable>
              ) : null}
              <View style={styles.headingCopy}>
                <Text style={styles.title}>{title}</Text>
                {subtitle ? (
                  <Text style={styles.subtitle}>{subtitle}</Text>
                ) : null}
              </View>
            </View>
            {action}
          </View>
          {children}
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

export const ui = StyleSheet.create({
  card: {
    padding: 16,
    borderWidth: 1,
    borderColor: "#E2E7E4",
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
  },
  input: {
    minHeight: 50,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: "#DCE3DF",
    borderRadius: Radius.small,
    backgroundColor: Palette.surface,
    color: Palette.ink,
    fontSize: 14,
  },
  textarea: {
    minHeight: 130,
    padding: 14,
    textAlignVertical: "top",
    borderWidth: 1,
    borderColor: "#DCE3DF",
    borderRadius: Radius.small,
    backgroundColor: Palette.surface,
    color: Palette.ink,
    fontSize: 14,
  },
  button: {
    minHeight: 48,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.small,
    backgroundColor: Palette.accent,
  },
  buttonDark: {
    minHeight: 48,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.small,
    backgroundColor: Palette.ink,
  },
  buttonSecondary: {
    minHeight: 44,
    paddingHorizontal: 15,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#DCE3DF",
    borderRadius: Radius.small,
    backgroundColor: Palette.surface,
  },
  buttonText: { color: "#FFFFFF", fontSize: 13, fontWeight: "900" },
  buttonSecondaryText: { color: Palette.ink, fontSize: 13, fontWeight: "800" },
  label: {
    marginBottom: 7,
    color: Palette.ink,
    fontSize: 12,
    fontWeight: "800",
  },
  muted: { color: Palette.muted, fontSize: 12, lineHeight: 18 },
  error: {
    padding: 12,
    borderRadius: Radius.small,
    backgroundColor: "#FFF0EE",
    color: "#B42318",
    fontSize: 12,
  },
  success: {
    padding: 12,
    borderRadius: Radius.small,
    backgroundColor: Palette.accentSoft,
    color: Palette.accent,
    fontSize: 12,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  grow: { minWidth: 0, flex: 1 },
  sectionTitle: { color: Palette.ink, fontSize: 18, fontWeight: "900" },
});

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#F5F7F6" },
  safe: { flex: 1 },
  content: {
    width: "100%",
    maxWidth: 760,
    alignSelf: "center",
    padding: Spacing.four,
    paddingBottom: 110,
    gap: Spacing.three,
  },
  header: {
    marginBottom: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  headingRow: {
    minWidth: 0,
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  headingCopy: { minWidth: 0, flex: 1 },
  back: {
    width: 38,
    height: 38,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 19,
    backgroundColor: Palette.surface,
  },
  backText: { marginTop: -3, color: Palette.ink, fontSize: 30 },
  title: {
    color: Palette.ink,
    fontSize: 28,
    fontWeight: "900",
    letterSpacing: -0.6,
  },
  subtitle: { marginTop: 5, color: Palette.muted, fontSize: 12 },
});
