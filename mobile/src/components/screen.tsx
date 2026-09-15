import { router } from "expo-router";
import { PropsWithChildren, ReactNode } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Palette, Radius, Shadow } from "@/constants/theme";
import { AppIcon } from "@/components/app-icon";

export const INPUT_PLACEHOLDER_COLOR = "#7A8580";

export function Screen({
  title,
  subtitle,
  children,
  back = false,
  action,
  footer,
}: PropsWithChildren<{
  title: string;
  subtitle?: string;
  back?: boolean;
  action?: ReactNode;
  footer?: ReactNode;
}>) {
  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.header}>
            <View style={styles.appBar}>
              {back ? (
                <Pressable
                  accessibilityLabel="뒤로 가기"
                  accessibilityRole="button"
                  hitSlop={10}
                  onPress={() => router.back()}
                  style={({ pressed }) => [styles.back, pressed && styles.pressed]}
                >
                  <AppIcon ios="chevron.left" android="arrow_back" size={22} color={Palette.ink} />
                </Pressable>
              ) : (
                <View style={styles.miniPin}><View style={styles.miniPinDot} /></View>
              )}
              <View style={styles.brandCopy}>
                <Text style={styles.brand}>여기일지도</Text>
                <Text style={styles.brandCaption}>LIFE MAP</Text>
              </View>
              <View style={styles.appBarAction}>{action}</View>
            </View>
            <View style={styles.headingCopy}>
              <Text style={styles.title}>{title}</Text>
              {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
            </View>
          </View>
          {children}
        </ScrollView>
        {footer ? (
          <SafeAreaView edges={["bottom"]} style={styles.footer}>
            {footer}
          </SafeAreaView>
        ) : null}
      </SafeAreaView>
    </KeyboardAvoidingView>
  );
}

export const ui = StyleSheet.create({
  card: {
    padding: 16,
    borderWidth: 1,
    borderColor: Palette.border,
    borderRadius: Radius.medium,
    backgroundColor: Palette.surface,
    boxShadow: Shadow.card,
  },
  input: {
    minHeight: 48,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: Palette.border,
    borderRadius: Radius.small,
    backgroundColor: Palette.surface,
    color: Palette.ink,
    fontSize: 15,
  },
  textarea: {
    minHeight: 130,
    padding: 14,
    textAlignVertical: "top",
    borderWidth: 1,
    borderColor: Palette.border,
    borderRadius: Radius.small,
    backgroundColor: Palette.surface,
    color: Palette.ink,
    fontSize: 15,
  },
  button: {
    minHeight: 46,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.medium,
    backgroundColor: Palette.accent,
  },
  buttonDark: {
    minHeight: 46,
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
    borderColor: Palette.border,
    borderRadius: Radius.small,
    backgroundColor: Palette.surface,
  },
  buttonText: { color: "#FFFFFF", fontSize: 14, fontWeight: "900" },
  buttonSecondaryText: { color: Palette.ink, fontSize: 14, fontWeight: "800" },
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
    backgroundColor: Palette.dangerSoft,
    color: Palette.danger,
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
  sectionTitle: { color: Palette.ink, fontSize: 19, fontWeight: "900", letterSpacing: -0.35 },
});

const styles = StyleSheet.create({
  footer: {
    padding: 12,
    gap: 8,
    backgroundColor: Palette.canvas,
    borderTopWidth: 1,
    borderColor: "#DCE3DF",
  },
  screen: { flex: 1, backgroundColor: Palette.canvas },
  safe: { flex: 1 },
  content: {
    width: "100%",
    maxWidth: 760,
    alignSelf: "center",
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 110,
    gap: 14,
  },
  header: {
    marginBottom: 7,
    gap: 20,
  },
  appBar: {
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  appBarAction: { marginLeft: "auto" },
  miniPin: { width: 29, height: 33, alignItems: "center", paddingTop: 7, borderTopLeftRadius: 15, borderTopRightRadius: 15, borderBottomLeftRadius: 15, backgroundColor: Palette.accent, transform: [{ rotate: "45deg" }] },
  miniPinDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: "#FFFFFF" },
  brandCopy: { justifyContent: "center" },
  brand: { color: Palette.ink, fontSize: 15, fontWeight: "900", letterSpacing: -0.4 },
  brandCaption: { marginTop: 1, color: Palette.muted, fontSize: 6, fontWeight: "800", letterSpacing: 1.4 },
  headingCopy: { minWidth: 0, flex: 1 },
  back: {
    width: 38,
    height: 38,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 19,
    backgroundColor: "transparent",
  },
  pressed: { opacity: 0.62, transform: [{ scale: 0.97 }] },
  title: {
    color: Palette.ink,
    fontSize: 24,
    fontWeight: "900",
    letterSpacing: -0.6,
  },
  subtitle: { marginTop: 3, color: Palette.muted, fontSize: 12, lineHeight: 18 },
});
