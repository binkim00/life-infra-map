import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useFormDraft } from "@/hooks/use-form-draft";
import {
  Alert,
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { boardsApi } from "@/api/boards";
import { useAuth } from "@/auth/auth-context";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { authorTierDisplay, type AuthorTierData } from "@/utils/tier-display";

type Comment = AuthorTierData & {
  id: number;
  author?: number;
  author_nickname?: string;
  author_username?: string;
  content: string;
  likes_count?: number;
  dislikes_count?: number;
  replies?: Comment[];
};
type Post = AuthorTierData & {
  id: number;
  author?: number;
  author_nickname?: string;
  author_username?: string;
  title: string;
  content: string;
  image_url?: string;
  likes_count?: number;
  is_liked?: boolean;
  view_count?: number;
  comments?: Comment[];
};

export default function BoardDetailScreen() {
  const { boardType = "free", postId = "" } = useLocalSearchParams<{
    boardType: string;
    postId: string;
  }>();
  const { user, requireLogin } = useAuth();
  const draft = useFormDraft(`post-interaction:${postId}`, { comment: "", reportReason: "", commentReportDrafts: {} as Record<number, string>, replyDrafts: {} as Record<number, string>, editingId: null as number | null, editingText: "" });
  const { comment, reportReason, commentReportDrafts, replyDrafts, editingId, editingText } = draft.value;
  const setComment = (value: typeof comment | ((current: typeof comment) => typeof comment)) => draft.update("comment", value);
  const setReportReason = (value: typeof reportReason | ((current: typeof reportReason) => typeof reportReason)) => draft.update("reportReason", value);
  const setCommentReportDrafts = (value: typeof commentReportDrafts | ((current: typeof commentReportDrafts) => typeof commentReportDrafts)) => draft.update("commentReportDrafts", value);
  const setReplyDrafts = (value: typeof replyDrafts | ((current: typeof replyDrafts) => typeof replyDrafts)) => draft.update("replyDrafts", value);
  const setEditingId = (value: typeof editingId | ((current: typeof editingId) => typeof editingId)) => draft.update("editingId", value);
  const setEditingText = (value: typeof editingText | ((current: typeof editingText) => typeof editingText)) => draft.update("editingText", value);
  const [error, setError] = useState("");
  const deleteAction = useAction();
  const interaction = useAction();
  const { data: post, loading, error: loadError, reload: load } = useResource<Post | null>(
    () => boardsApi.post(postId).then(data => data as unknown as Post), null, true, postId,
  );
  const addComment = () => interaction.run(async () => {
    if (!requireLogin() || !comment.trim()) return;
    await boardsApi.createComment(postId, { content: comment.trim() });
    setComment("");
    await load();
  });
  const remove = () => Alert.alert("게시글 삭제", "삭제한 게시글은 복구할 수 없습니다. 삭제할까요?", [
    { text: "취소", style: "cancel" },
    { text: "삭제", style: "destructive", onPress: () => deleteAction.run(async () => {
      await boardsApi.deletePost(postId);
      router.replace(`/boards/${boardType}` as never);
    }) },
  ]);
  if (!post)
    return (
      <Screen title="게시글" back>
        <LoadState loading={loading} error={loadError} empty={!post} retry={load} />
      </Screen>
    );
  return (
    <Screen
      title={post.title}
      subtitle={<Text style={{ color: authorTierDisplay(post).color }}>{`${post.author_nickname || post.author_username} · ${authorTierDisplay(post).label} · 조회 ${post.view_count || 0}`}</Text>}
      back
    >
      {draft.error ? <Text style={ui.error}>{draft.error}</Text> : null}
      {deleteAction.error ? <Text style={ui.error}>{deleteAction.error}</Text> : null}
      {interaction.error ? <Text style={ui.error}>{interaction.error}</Text> : null}
      <View style={ui.card}>
        <Text style={styles.content}>{post.content}</Text>
        {post.image_url ? (
          <Image source={{ uri: post.image_url }} style={styles.image} />
        ) : null}
      </View>
      <View style={ui.row}>
        <Pressable
          disabled={!draft.ready || interaction.busy}
          onPress={() => interaction.run(async () => {
            if (!requireLogin()) return;
            await boardsApi.likePost(postId);
            await load();
          })}
          style={ui.buttonSecondary}
        >
          <Text style={ui.buttonSecondaryText}>
            좋아요 {post.likes_count || 0}
          </Text>
        </Pressable>
        {user?.id === post.author ? (
          <>
            <Pressable
              onPress={() =>
                router.push(`/boards/${boardType}/${postId}/edit` as never)
              }
              style={ui.buttonSecondary}
            >
              <Text style={ui.buttonSecondaryText}>수정</Text>
            </Pressable>
            <Pressable onPress={remove} style={ui.buttonSecondary}>
              <Text style={styles.deleteText}>삭제</Text>
            </Pressable>
          </>
        ) : null}
      </View>
      <View style={ui.row}>
        <TextInput
          value={reportReason}
          onChangeText={setReportReason}
          placeholder="신고 사유"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={[ui.input, ui.grow]}
        />
        <Pressable
          disabled={!draft.ready || interaction.busy || !reportReason.trim()}
          onPress={() => interaction.run(async () => {
            if (!requireLogin() || !reportReason.trim()) return;
            await boardsApi.reportPost(postId, { reason: reportReason.trim() });
            setReportReason("");
            setError("신고가 접수되었습니다.");
          })}
          style={ui.buttonSecondary}
        >
          <Text style={styles.deleteText}>게시글 신고</Text>
        </Pressable>
      </View>
      {error ? (
        <Text style={error.includes("접수되었습니다.") ? ui.success : ui.error}>
          {error}
        </Text>
      ) : null}
      <Text style={ui.sectionTitle}>댓글 {post.comments?.length || 0}</Text>
      <View style={ui.row}>
        <TextInput
          value={comment}
          onChangeText={setComment}
          placeholder="댓글을 입력하세요"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={[ui.input, ui.grow]}
        />
        <Pressable disabled={!draft.ready || interaction.busy || !comment.trim()} onPress={addComment} style={[ui.button, !comment.trim() && styles.disabled]}>
          <Text style={ui.buttonText}>등록</Text>
        </Pressable>
      </View>
      <View style={styles.comments}>
        {post.comments?.map((item) => (
          <View key={item.id} style={ui.card}>
            <Text style={[styles.author, { color: authorTierDisplay(item).color }]}>
              {item.author_nickname || item.author_username} · {authorTierDisplay(item).label}
            </Text>
            {editingId === item.id ? (
              <View style={ui.row}>
                <TextInput
                  value={editingText}
                  onChangeText={setEditingText}
                  placeholder="댓글 수정 내용"
                  placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                  style={[ui.input, ui.grow]}
                />
                <Pressable
                  disabled={!draft.ready || interaction.busy || !editingText.trim()}
                  onPress={() => interaction.run(async () => {
                    await boardsApi.updateComment(item.id, { content: editingText.trim() });
                    setEditingId(null);
                    await load();
                  })}
                  style={ui.buttonSecondary}
                >
                  <Text style={ui.buttonSecondaryText}>저장</Text>
                </Pressable>
              </View>
            ) : (
              <Text style={styles.comment}>{item.content}</Text>
            )}
            <View style={[ui.row, styles.commentActions]}>
              <Pressable
                disabled={!draft.ready || interaction.busy}
                onPress={() => interaction.run(async () => {
                  if (!requireLogin()) return;
                  await boardsApi.likeComment(item.id);
                  await load();
                })}
              >
                <Text style={styles.action}>
                  좋아요 {item.likes_count || 0}
                </Text>
              </Pressable>
              <Pressable
                disabled={!draft.ready || interaction.busy}
                onPress={() => interaction.run(async () => {
                  if (!requireLogin()) return;
                  await boardsApi.dislikeComment(item.id);
                  await load();
                })}
              >
                <Text style={styles.action}>
                  싫어요 {item.dislikes_count || 0}
                </Text>
              </Pressable>
              {user?.id === item.author ? (
                <>
                  <Pressable
                    onPress={() => {
                      setEditingId(item.id);
                      setEditingText(item.content);
                    }}
                  >
                    <Text style={styles.action}>수정</Text>
                  </Pressable>
                  <Pressable onPress={() => Alert.alert("댓글 삭제", "이 댓글을 삭제할까요?", [
                    { text: "취소", style: "cancel" },
                    { text: "삭제", style: "destructive", onPress: () => interaction.run(async () => { await boardsApi.deleteComment(item.id); await load(); }) },
                  ])}>
                    <Text style={styles.deleteText}>삭제</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
            <View style={[ui.row, styles.commentReport]}>
              <TextInput
                value={commentReportDrafts[item.id] || ""}
                onChangeText={(value) => setCommentReportDrafts((current) => ({ ...current, [item.id]: value }))}
                placeholder="댓글 신고 사유"
                placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                style={[ui.input, styles.reportInput]}
              />
              <Pressable
                disabled={!draft.ready || interaction.busy || !commentReportDrafts[item.id]?.trim()}
                onPress={() => interaction.run(async () => {
                  const reason = commentReportDrafts[item.id]?.trim();
                  if (!requireLogin() || !reason) return;
                  await boardsApi.reportComment(item.id, { reason });
                  setCommentReportDrafts((current) => ({ ...current, [item.id]: "" }));
                  setError("댓글 신고가 접수되었습니다.");
                })}
              ><Text style={styles.deleteText}>신고</Text></Pressable>
            </View>
            <View style={[ui.row, styles.replyBox]}>
              <TextInput
                value={replyDrafts[item.id] || ""}
                onChangeText={(value) =>
                  setReplyDrafts((current) => ({
                    ...current,
                    [item.id]: value,
                  }))
                }
                placeholder="답글"
                placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                style={[ui.input, ui.grow]}
              />
              <Pressable
                disabled={!draft.ready || interaction.busy || !replyDrafts[item.id]?.trim()}
                onPress={() => interaction.run(async () => {
                  const content = replyDrafts[item.id]?.trim();
                  if (!requireLogin() || !content) return;
                  await boardsApi.createComment(postId, {
                    content,
                    parent: item.id,
                  });
                  setReplyDrafts((current) => ({ ...current, [item.id]: "" }));
                  await load();
                })}
                style={ui.buttonSecondary}
              >
                <Text style={ui.buttonSecondaryText}>답글</Text>
              </Pressable>
            </View>
            {item.replies?.map((reply) => (
              <View key={reply.id} style={styles.reply}>
                <Text style={[styles.author, { color: authorTierDisplay(reply).color }]}>
                  {reply.author_nickname || reply.author_username} · {authorTierDisplay(reply).label}
                </Text>
                <Text style={styles.comment}>{reply.content}</Text>
              </View>
            ))}
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  content: { color: "#222222", fontSize: 14, lineHeight: 23 },
  image: {
    width: "100%",
    height: 260,
    marginTop: 14,
    borderRadius: 12,
    resizeMode: "cover",
  },
  comments: { gap: 8 },
  author: { color: "#222222", fontSize: 12, fontWeight: "900" },
  comment: {
    marginVertical: 9,
    color: "#38403C",
    fontSize: 13,
    lineHeight: 20,
  },
  action: { color: "#0F766E", fontSize: 11, fontWeight: "800" },
  commentActions: { flexWrap: "wrap" },
  commentReport: { marginTop: 10 },
  replyBox: { marginTop: 10 },
  reply: {
    marginTop: 10,
    marginLeft: 16,
    padding: 12,
    borderRadius: 10,
    backgroundColor: "#F5F7F6",
  },
  deleteText: { color: "#B42318", fontSize: 11, fontWeight: "800" },
  reportInput: { minWidth: 120, flex: 1, minHeight: 42, fontSize: 12 },
  disabled: { opacity: 0.45 },
});
