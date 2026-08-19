import { StyleSheet, Text, View } from "react-native";
import { Screen, ui } from "@/components/screen";
const TIERS = [
  ["아이언", 0],
  ["브론즈", 50],
  ["실버", 100],
  ["골드", 200],
  ["플래티넘", 300],
  ["다이아", 500],
  ["마스터", 700],
  ["챌린저", 1000],
] as const;
const RULES = [
  ["게시글 작성", "일일 1~5개당 +1"],
  ["댓글 작성", "일일 1~10개당 +1"],
  ["태그 제보 승인", "+10"],
  ["오류/수정 제보 승인", "+5"],
  ["새 장소 제보 승인", "+20"],
];
export default function UpgradeGuideScreen() {
  return (
    <Screen
      title="승급가이드"
      subtitle="활동과 승인된 제보를 기준으로 티어가 계산됩니다."
      back
    >
      <Text style={ui.sectionTitle}>기여도 반영 기준</Text>
      <View style={styles.grid}>
        {RULES.map(([label, score]) => (
          <View key={label} style={[ui.card, styles.rule]}>
            <Text style={styles.name}>{label}</Text>
            <Text style={styles.score}>{score}</Text>
          </View>
        ))}
      </View>
      <Text style={ui.sectionTitle}>티어별 조건</Text>
      <View style={styles.list}>
        {TIERS.map(([name, score]) => (
          <View key={name} style={[ui.card, styles.tier]}>
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{name.slice(0, 1)}</Text>
            </View>
            <View style={ui.grow}>
              <Text style={styles.name}>{name}</Text>
              <Text style={ui.muted}>
                {score === 0 ? "기본 티어" : `기여도 ${score} 이상`}
              </Text>
            </View>
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  grid: { gap: 8 },
  rule: { flexDirection: "row", alignItems: "center" },
  list: { gap: 8 },
  tier: { flexDirection: "row", alignItems: "center", gap: 12 },
  badge: {
    width: 38,
    height: 38,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 12,
    backgroundColor: "#E6F4F1",
  },
  badgeText: { color: "#0F766E", fontSize: 13, fontWeight: "900" },
  name: { flex: 1, color: "#222222", fontSize: 13, fontWeight: "900" },
  score: { color: "#0F766E", fontSize: 12, fontWeight: "900" },
});
