import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Screen, ui } from "@/components/screen";
const ROWS = [
  [
    "1. 상황 맞춤 추천",
    "지역과 상황, 꼭 필요한 조건을 말하면 근거와 함께 장소를 추천합니다.",
    "/recommend",
  ],
  [
    "2. 일반 장소 검색",
    "장소명이나 지역·업종을 검색하고 지도 이동 후 그 지역에서 다시 찾을 수 있습니다.",
    "/explore",
  ],
  [
    "3. 장소 저장",
    "마음에 드는 장소를 원하는 이름의 그룹에 나누고 메모를 남길 수 있습니다.",
    "/mypage/saved-places",
  ],
  [
    "4. 장소 제보",
    "검색되지 않는 장소나 달라진 정보를 지도 핀과 사진으로 알려주세요.",
    "/place-report",
  ],
  [
    "5. 커뮤니티",
    "장소 팁을 나누고 부적절한 게시글이나 댓글은 신고할 수 있습니다.",
    "/boards/free",
  ],
  [
    "6. 문의하기",
    "고객센터에 문의를 남기면 답변 상태와 내용을 확인할 수 있습니다.",
    "/inquiries/new",
  ],
] as const;
export default function GuideScreen() {
  return (
    <Screen title="이용가이드" subtitle="서비스의 주요 기능을 안내합니다." back>
      <View style={styles.list}>
        {ROWS.map(([title, description, path]) => (
          <View key={title} style={ui.card}>
            <Text style={styles.title}>{title}</Text>
            <Text style={styles.description}>{description}</Text>
            <Pressable onPress={() => router.push(path as never)} style={styles.startButton}>
              <Text style={styles.startText}>바로 시작 ›</Text>
            </Pressable>
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
  startButton: { marginTop: 12, minHeight: 38, alignSelf: "flex-start", justifyContent: "center" },
  startText: { color: "#0F857A", fontSize: 12, fontWeight: "900" },
});
