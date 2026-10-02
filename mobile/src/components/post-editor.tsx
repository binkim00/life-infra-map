import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";
import { ApiError } from "@/api/client";
import { useState } from "react";
import { useResource } from "@/hooks/use-resource";
import { LoadState } from "./load-state";
import {
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { boardsApi } from "@/api/boards";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";

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
  const { loading: fetching, error: loadError, reload } = useResource(async () => {
    if (postId) {
      const post = await boardsApi.post(postId);
        setTitle(String(post.title || ""));
        setContent(String(post.content || ""));
    }
  }, undefined, Boolean(postId), postId || "new");
  const pick = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError("사진을 첨부하려면 사진 접근 권한을 허용해 주세요.");
      return;
    }
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
    } catch (cause) {
      const payload = cause instanceof ApiError
        ? cause.data as { penalty?: { is_suspended?: boolean } } | null : null;
      setError(payload?.penalty?.is_suspended
        ? "활동 정지 중에는 게시글을 작성하거나 수정할 수 없습니다. 해제 후 다시 시도해 주세요."
        : cause instanceof ApiError ? cause.message : "게시글을 저장하지 못했습니다.");
    } finally {
      setLoading(false);
    }
  };
  return (
    <Screen title={postId ? "게시글 수정" : "새 게시글"} subtitle="이웃에게 도움이 되는 장소 정보와 경험을 나눠주세요." back>
      {postId ? <LoadState loading={fetching} error={loadError} retry={reload} /> : null}
      <View style={styles.guide}><Text style={styles.guideMark}>✦</Text><Text style={styles.guideText}>개인정보나 광고성 내용은 숨김 처리될 수 있어요.</Text></View>
      <View style={styles.form}>
        <Text style={ui.label}>제목</Text>
        <TextInput
          value={title}
          onChangeText={setTitle}
          placeholder="제목"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={ui.input}
        />
        <Text style={ui.label}>내용</Text>
        <TextInput
          value={content}
          onChangeText={setContent}
          placeholder="내용"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          multiline
          style={ui.textarea}
        />
        <Pressable accessibilityRole="button" onPress={pick} style={styles.photoButton}>
          <Text style={styles.photoIcon}>＋</Text><View><Text style={styles.photoTitle}>사진 첨부</Text><Text style={styles.photoCopy}>장소나 정보를 잘 보여주는 사진을 선택하세요.</Text></View>
        </Pressable>
        {image ? (
          <View style={styles.imageWrap}>
            <Image source={{ uri: image.uri }} style={styles.image} />
            <Pressable accessibilityRole="button" onPress={() => setImage(null)} style={styles.removeImage}>
              <Text style={styles.removeImageText}>사진 제거</Text>
            </Pressable>
          </View>
        ) : null}
        {error ? <Text style={ui.error}>{error}</Text> : null}
        <Pressable disabled={loading || Boolean(postId && (fetching || loadError))} onPress={submit} style={ui.button}>
          <Text style={ui.buttonText}>{loading ? "저장 중..." : "저장"}</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  form: { gap: 12 },
  guide: { padding: 13, flexDirection: "row", alignItems: "center", gap: 9, borderRadius: Radius.medium, backgroundColor: Palette.accentSoft },
  guideMark: { color: Palette.accent, fontSize: 18, fontWeight: "900" },
  guideText: { color: Palette.accentDark, fontSize: 11, fontWeight: "700" },
  photoButton: { minHeight: 68, paddingHorizontal: 14, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1, borderStyle: "dashed", borderColor: Palette.accent, borderRadius: Radius.medium, backgroundColor: Palette.surface },
  photoIcon: { color: Palette.accent, fontSize: 24, fontWeight: "500" },
  photoTitle: { color: Palette.ink, fontSize: 13, fontWeight: "900" },
  photoCopy: { marginTop: 3, color: Palette.muted, fontSize: 9 },
  image: { width: "100%", height: 220, borderRadius: 12, resizeMode: "cover" },
  imageWrap: { gap: 8 },
  removeImage: { minHeight: 40, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#F0BABA", borderRadius: 12, backgroundColor: "#FFF0F0" },
  removeImageText: { color: "#D94B4B", fontSize: 12, fontWeight: "900" },
});
