import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
const CATEGORIES = [["general", "일반 문의"], ["service_issue", "서비스 불편"], ["bug", "오류 신고"]] as const;
export default function InquiryCreateScreen() {
  const [category, setCategory] = useState<(typeof CATEGORIES)[number][0]>("general");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async () => {
    if (!title.trim() || content.trim().length < 5)
      return setError("제목과 5자 이상의 내용을 입력해주세요.");
    try {
      setLoading(true);
      await boardsApi.createInquiry({ title, content, category });
      router.replace("/inquiries/my");
    } catch {
      setError("문의 등록에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };
  return (
    <Screen
      title="문의하기"
      subtitle="서비스 이용 중 궁금한 점을 남겨주세요."
      back
    >
      <View style={styles.notice}><Text style={styles.noticeIcon}>?</Text><View style={ui.grow}><Text style={styles.noticeTitle}>문의 전 확인해 주세요</Text><Text style={styles.noticeCopy}>장소 제보나 정보 수정은 장소 제보 메뉴를 이용하면 더 빠르게 처리됩니다.</Text></View></View>
      <View style={styles.form}>
        <Text style={ui.label}>문의 유형</Text>
        <View style={styles.categories}>{CATEGORIES.map(([value, label]) => <Pressable key={value} onPress={() => setCategory(value)} style={[styles.category, category === value && styles.categorySelected]}><Text style={category === value ? styles.categorySelectedText : styles.categoryText}>{label}</Text></Pressable>)}</View>
        <Text style={ui.label}>문의 제목</Text>
        <TextInput
          value={title}
          onChangeText={setTitle}
          placeholder="문의 제목"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={ui.input}
        />
        <Text style={ui.label}>문의 내용</Text>
        <TextInput
          value={content}
          onChangeText={setContent}
          placeholder="문의 내용"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          multiline
          style={ui.textarea}
        />
        {error ? <Text style={ui.error}>{error}</Text> : null}
        <Pressable disabled={loading} onPress={submit} style={ui.button}>
          <Text style={ui.buttonText}>
            {loading ? "등록 중..." : "문의 등록"}
          </Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  categories: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  category: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: Radius.pill, backgroundColor: Palette.accentSoft },
  categorySelected: { backgroundColor: Palette.ink },
  categoryText: { color: Palette.ink, fontWeight: "700" },
  categorySelectedText: { color: "#FFFFFF", fontWeight: "700" },
  form: { gap: 10 },
  notice: { padding: 15, flexDirection: "row", alignItems: "center", gap: 11, borderRadius: Radius.medium, backgroundColor: Palette.accentSoft },
  noticeIcon: { width: 32, color: Palette.accent, fontSize: 22, fontWeight: "900" },
  noticeTitle: { color: Palette.accentDark, fontSize: 13, fontWeight: "900" },
  noticeCopy: { marginTop: 4, color: Palette.muted, fontSize: 10, lineHeight: 16 },
});
