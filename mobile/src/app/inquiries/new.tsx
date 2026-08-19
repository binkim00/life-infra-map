import { router } from "expo-router";
import { useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import { boardsApi } from "@/api/boards";
import { Screen, ui } from "@/components/screen";
export default function InquiryCreateScreen() {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async () => {
    if (!title.trim() || content.trim().length < 5)
      return setError("제목과 5자 이상의 내용을 입력해주세요.");
    try {
      setLoading(true);
      await boardsApi.createInquiry({ title, content });
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
      <View style={{ gap: 12 }}>
        <TextInput
          value={title}
          onChangeText={setTitle}
          placeholder="문의 제목"
          style={ui.input}
        />
        <TextInput
          value={content}
          onChangeText={setContent}
          placeholder="문의 내용"
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
