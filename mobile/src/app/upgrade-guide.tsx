import { StyleSheet, Text, View } from "react-native";
import { Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
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
  ["게시글·댓글 활동", "하루 합산 최대 +5"],
  ["태그 제보 승인", "+10"],
  ["오류/수정 제보 승인", "+5"],
  ["새 장소 제보 승인", "+20"],
];
export default function UpgradeGuideScreen() {
  return (
    <Screen
      title="등급 안내"
      subtitle="게시글·댓글 활동과 승인된 장소 제보를 기준으로 등급이 계산됩니다."
      back
    >
      <View style={[ui.card, styles.notice]}>
        <View style={styles.noticeIcon}><Text style={styles.noticeIconText}>↑</Text></View>
        <View style={ui.grow}>
        <Text style={styles.noticeTitle}>승인된 기여만 점수에 반영돼요</Text>
        <Text style={ui.muted}>제보는 운영 검토가 끝난 뒤 반영되며, 반려되거나 중복인 내용은 점수에 포함되지 않습니다.</Text>
        </View>
      </View>
      <Text style={ui.sectionTitle}>기여도 반영 기준</Text>
      <View style={styles.grid}>
        {RULES.map(([label, score]) => (
          <View key={label} style={[ui.card, styles.rule]}>
            <Text style={styles.name}>{label}</Text>
            <Text style={styles.score}>{score}</Text>
          </View>
        ))}
      </View>
      <Text style={ui.sectionTitle}>등급별 조건</Text>
      <View style={styles.list}>
        {TIERS.map(([name, score]) => (
          <View key={name} style={[ui.card, styles.tier]}>
            <View style={[styles.badge, { backgroundColor: score >= 500 ? Palette.ink : score >= 200 ? Palette.amberSoft : Palette.accentSoft }]}>
              <Text style={styles.badgeText}>{name.slice(0, 1)}</Text>
            </View>
            <View style={ui.grow}>
              <Text style={styles.name}>{name}</Text>
              <Text style={ui.muted}>
                {score === 0 ? "기본 등급" : `기여도 ${score} 이상`}
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
  rule: { flexDirection: "row", alignItems: "center", minHeight: 54 },
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
  badgeText: { color: Palette.accent, fontSize: 13, fontWeight: "900" },
  name: { flex: 1, color: "#222222", fontSize: 13, fontWeight: "900" },
  score: { color: "#0F766E", fontSize: 12, fontWeight: "900" },
  notice: { flexDirection: "row", alignItems: "center", gap: 12, borderColor: "#B9DED5", backgroundColor: "#EFF8F5" },
  noticeIcon: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: Radius.medium, backgroundColor: Palette.accent },
  noticeIconText: { color: "#FFFFFF", fontSize: 20, fontWeight: "900" },
  noticeTitle: { marginBottom: 6, color: "#0F6F66", fontSize: 14, fontWeight: "900" },
});
