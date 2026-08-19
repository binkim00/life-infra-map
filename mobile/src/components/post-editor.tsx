import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import {
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { boardsApi } from "@/api/boards";
import { Screen, ui } from "@/components/screen";

export function PostEditor({
  boardType,
  postId,
}: {
  boardType: string;
  postId?: string;
}) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [image, setImage] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (postId)
      boardsApi.post(postId).then((post) => {
        setTitle(String(post.title || ""));
        setContent(String(post.content || ""));
      });
  }, [postId]);
  const pick = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.85,
    });
    if (!result.canceled) setImage(result.assets[0]);
  };
  const submit = async () => {
    if (!title.trim() || !content.trim())
      return setError("제목과 내용을 입력해주세요.");
    const body = new FormData();
    body.append("board_type", boardType);
    body.append("title", title.trim());
    body.append("content", content.trim());
    if (image)
      body.append("image", {
        uri: image.uri,
        name: image.fileName || "post.jpg",
        type: image.mimeType || "image/jpeg",
      } as unknown as Blob);
    try {
      setLoading(true);
      setError("");
      const result = postId
        ? await boardsApi.updatePost(postId, body)
        : await boardsApi.createPost(body);
      const created = result as { id?: number | string };
      const id = postId || String(created.id);
      router.replace(`/boards/${boardType}/${id}` as never);
    } catch {
      setError("게시글을 저장하지 못했습니다.");
    } finally {
      setLoading(false);
    }
  };
  return (
    <Screen title={postId ? "게시글 수정" : "새 게시글"} back>
      <View style={styles.form}>
        <TextInput
          value={title}
          onChangeText={setTitle}
          placeholder="제목"
          style={ui.input}
        />
        <TextInput
          value={content}
          onChangeText={setContent}
          placeholder="내용"
          multiline
          style={ui.textarea}
        />
        <Pressable onPress={pick} style={ui.buttonSecondary}>
          <Text style={ui.buttonSecondaryText}>사진 선택</Text>
        </Pressable>
        {image ? (
          <Image source={{ uri: image.uri }} style={styles.image} />
        ) : null}
        {error ? <Text style={ui.error}>{error}</Text> : null}
        <Pressable disabled={loading} onPress={submit} style={ui.button}>
          <Text style={ui.buttonText}>{loading ? "저장 중..." : "저장"}</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  form: { gap: 12 },
  image: { width: "100%", height: 220, borderRadius: 12, resizeMode: "cover" },
});
