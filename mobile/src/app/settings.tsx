import AsyncStorage from "@react-native-async-storage/async-storage";
import { useState } from "react";
import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { StyleSheet, Switch, Text, View } from "react-native";
import { Screen, ui } from "@/components/screen";
const KEY = "lifeInfraSettings";
const DEFAULTS = {
  commentNotifications: true,
  inquiryNotifications: true,
  compactMode: false,
};
export default function SettingsScreen() {
  const [settings, setSettings] = useState(DEFAULTS);
  const { loading, error, reload } = useResource(async () => {
    const raw = await AsyncStorage.getItem(KEY);
      if (raw) setSettings({ ...DEFAULTS, ...JSON.parse(raw) });
  }, undefined);
  const toggle = (key: keyof typeof settings, value: boolean) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    AsyncStorage.setItem(KEY, JSON.stringify(next));
  };
  const rows: [keyof typeof settings, string, string][] = [
    [
      "commentNotifications",
      "새 댓글 알림",
      "내 글에 댓글이 달리면 알려줍니다.",
    ],
    [
      "inquiryNotifications",
      "문의 답변 알림",
      "고객센터 답변 등록 시 알려줍니다.",
    ],
    [
      "compactMode",
      "간결한 목록 보기",
      "장소와 게시글 목록을 촘촘하게 표시합니다.",
    ],
  ];
  return (
    <Screen title="설정" subtitle="알림과 화면 표시 방식을 관리합니다." back>
      <LoadState loading={loading} error={error} retry={reload} />
      <View style={styles.list}>
        {rows.map(([key, title, description]) => (
          <View key={key} style={[ui.card, styles.row]}>
            <View style={ui.grow}>
              <Text style={styles.title}>{title}</Text>
              <Text style={ui.muted}>{description}</Text>
            </View>
            <Switch
              disabled={loading || Boolean(error)}
              value={settings[key]}
              onValueChange={(value) => toggle(key, value)}
              trackColor={{ true: "#0F766E" }}
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
  title: { marginBottom: 5, color: "#222222", fontSize: 13, fontWeight: "900" },
});
