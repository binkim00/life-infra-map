import { StyleSheet, Text, View } from "react-native";
import { Screen, ui } from "@/components/screen";
const ROWS = [
  [
    "1. 장소 찾기",
    "홈에서 필요한 상황을 입력하면 주변 생활 인프라를 추천받을 수 있습니다.",
  ],
  [
    "2. 게시판 이용",
    "자유게시판에서 이용 팁을 공유하고 공지사항에서 운영 안내를 확인할 수 있습니다.",
  ],
  [
    "3. 문의하기",
    "고객센터에서 문의를 남기면 답변 등록 시 알림으로 안내됩니다.",
  ],
  [
    "4. 신고와 제재",
    "부적절한 게시글이나 댓글은 신고할 수 있으며 운영자가 검토 후 조치합니다.",
  ],
];
export default function GuideScreen() {
  return (
    <Screen title="이용가이드" subtitle="서비스의 주요 기능을 안내합니다." back>
      <View style={styles.list}>
        {ROWS.map(([title, description]) => (
          <View key={title} style={ui.card}>
            <Text style={styles.title}>{title}</Text>
            <Text style={styles.description}>{description}</Text>
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  title: { color: "#222222", fontSize: 14, fontWeight: "900" },
  description: { marginTop: 7, color: "#686159", fontSize: 12, lineHeight: 19 },
});
