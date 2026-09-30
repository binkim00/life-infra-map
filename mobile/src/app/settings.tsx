import AsyncStorage from "@react-native-async-storage/async-storage";
import { useState } from "react";
import { router } from "expo-router";
import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { Linking, Pressable, StyleSheet, Switch, Text, View } from "react-native";
import { useAuth } from "@/auth/auth-context";
import { Screen, ui } from "@/components/screen";
import { Palette } from "@/constants/theme";
const KEY = "lifeInfraSettings";
const DEFAULTS = {
  commentNotifications: true,
  inquiryNotifications: true,
  compactMode: false,
};
export default function SettingsScreen() {
  const { isLoggedIn } = useAuth();
  const [settings, setSettings] = useState(DEFAULTS);
  const [saveError, setSaveError] = useState("");
  const { loading, error, reload } = useResource(async () => {
    const raw = await AsyncStorage.getItem(KEY);
      if (raw) setSettings({ ...DEFAULTS, ...JSON.parse(raw) });
  }, undefined);
  const toggle = async (key: keyof typeof settings, value: boolean) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    setSaveError("");
    try {
      await AsyncStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      setSettings(settings);
      setSaveError("설정을 저장하지 못했습니다. 다시 시도해 주세요.");
    }
  };
  const rows: [keyof typeof settings, string, string, string][] = [
    [
      "commentNotifications",
      "새 댓글 알림",
      "내 글에 댓글이 달리면 알려줍니다.",
      "◌",
    ],
    [
      "inquiryNotifications",
      "문의 답변 알림",
      "고객센터 답변 등록 시 알려줍니다.",
      "?",
    ],
    [
      "compactMode",
      "간결한 목록 보기",
      "장소와 게시글 목록을 촘촘하게 표시합니다.",
      "≡",
    ],
  ];
  return (
    <Screen title="설정" subtitle="알림과 화면 표시 방식을 관리합니다." back>
      <LoadState loading={loading} error={error} retry={reload} />
      {saveError ? <Text style={ui.error}>{saveError}</Text> : null}
      <View style={styles.list}>
        {rows.map(([key, title, description, icon]) => (
          <View key={key} style={[ui.card, styles.row]}>
            <View style={styles.icon}><Text style={styles.iconText}>{icon}</Text></View>
            <View style={ui.grow}>
              <Text style={styles.title}>{title}</Text>
              <Text style={ui.muted}>{description}</Text>
            </View>
            <Switch
              disabled={loading || Boolean(error)}
              value={settings[key]}
              onValueChange={(value) => void toggle(key, value)}
              trackColor={{ false: "#CBD5D0", true: Palette.accent }}
              thumbColor="#FFFFFF"
            />
          </View>
        ))}
      </View>
      {isLoggedIn ? (
        <Pressable style={[ui.card, styles.row]} onPress={() => router.push("/account-deletion")}>
          <Text style={styles.title}>계정 삭제</Text>
          <Text style={ui.muted}>계정과 연관 데이터를 삭제합니다.</Text>
        </Pressable>
      ) : null}
      <Pressable style={[ui.card, styles.row]} onPress={() => void Linking.openURL("https://yeogiljido.com/privacy.html")}>
        <Text style={styles.title}>개인정보처리방침</Text>
      </Pressable>
      <Pressable style={[ui.card, styles.row]} onPress={() => void Linking.openURL("https://yeogiljido.com/support.html")}>
        <Text style={styles.title}>고객 지원</Text>
      </Pressable>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  icon: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 13, backgroundColor: Palette.surfaceMuted },
  iconText: { color: Palette.accent, fontSize: 17, fontWeight: "900" },
  title: { marginBottom: 5, color: "#222222", fontSize: 13, fontWeight: "900" },
});
