import { useState } from "react";
import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { StyleSheet, Switch, Text, View } from "react-native";
import { Screen, ui } from "@/components/screen";
import { Palette } from "@/constants/theme";
import { DEFAULT_NOTIFICATION_SETTINGS, readNotificationSettings, writeNotificationSettings } from "@/utils/notification-settings";
export default function SettingsScreen() {
  const [settings, setSettings] = useState(DEFAULT_NOTIFICATION_SETTINGS);
  const [saveError, setSaveError] = useState("");
  const { loading, error, reload } = useResource(async () => {
    setSettings(await readNotificationSettings());
  }, undefined);
  const toggle = async (key: keyof typeof settings, value: boolean) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    setSaveError("");
    try {
      await writeNotificationSettings(next);
    } catch {
      setSettings(settings);
      setSaveError("설정을 저장하지 못했습니다. 다시 시도해 주세요.");
    }
  };
  const rows: [keyof typeof settings, string, string, string][] = [
    [
      "commentNotifications",
      "새 댓글 알림",
      "내 글의 새 댓글 알림을 목록에 표시합니다.",
      "◌",
    ],
    [
      "inquiryNotifications",
      "문의 답변 알림",
      "문의 답변 알림을 목록에 표시합니다.",
      "?",
    ],
  ];
  return (
    <Screen title="설정" subtitle="이 기기의 알림 목록 표시를 관리합니다." back>
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
