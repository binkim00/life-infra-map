import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { boardsApi } from "@/api/boards";
import { useAuth } from "@/auth/auth-context";
import { Screen, ui } from "@/components/screen";

type Comment = {
  id: number;
  author?: number;
  author_nickname?: string;
  author_username?: string;
  content: string;
  likes_count?: number;
  dislikes_count?: number;
  replies?: Comment[];
};
type Post = {
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
  const [post, setPost] = useState<Post | null>(null);
  const [comment, setComment] = useState("");
  const [reportReason, setReportReason] = useState("");
  const [replyDrafts, setReplyDrafts] = useState<Record<number, string>>({});
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(
    () =>
      boardsApi
        .post(postId)
        .then((data) => setPost(data as unknown as Post))
        .catch(() => setError("게시글을 불러오지 못했습니다.")),
    [postId],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const addComment = async () => {
    if (!requireLogin() || !comment.trim()) return;
    try {
      await boardsApi.createComment(postId, { content: comment.trim() });
      setComment("");
      void load();
    } catch {
      setError("댓글을 등록하지 못했습니다.");
    }
  };
  const remove = async () => {
    await boardsApi.deletePost(postId);
    router.replace(`/boards/${boardType}` as never);
  };
  if (!post)
    return (
      <Screen title="게시글" back>
        {error ? (
          <Text style={ui.error}>{error}</Text>
        ) : (
          <ActivityIndicator color="#0F766E" />
        )}
      </Screen>
    );
  return (
    <Screen
      title={post.title}
      subtitle={`${post.author_nickname || post.author_username} · 조회 ${post.view_count || 0}`}
      back
    >
      <View style={ui.card}>
        <Text style={styles.content}>{post.content}</Text>
        {post.image_url ? (
          <Image source={{ uri: post.image_url }} style={styles.image} />
        ) : null}
      </View>
      <View style={ui.row}>
        <Pressable
          onPress={async () => {
            if (requireLogin()) {
              try {
                await boardsApi.likePost(postId);
                void load();
              } catch {
                setError("좋아요를 반영하지 못했습니다.");
              }
            }
          }}
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
          style={[ui.input, ui.grow]}
        />
        <Pressable
          onPress={async () => {
            if (!requireLogin() || !reportReason.trim()) return;
            try {
              await boardsApi.reportPost(postId, { reason: reportReason.trim() });
              setReportReason("");
              setError("신고가 접수되었습니다.");
            } catch {
              setError("신고를 접수하지 못했습니다.");
            }
          }}
          style={ui.buttonSecondary}
        >
          <Text style={styles.deleteText}>게시글 신고</Text>
        </Pressable>
      </View>
      {error ? (
        <Text style={error === "신고가 접수되었습니다." ? ui.success : ui.error}>
          {error}
        </Text>
      ) : null}
      <Text style={ui.sectionTitle}>댓글 {post.comments?.length || 0}</Text>
      <View style={ui.row}>
        <TextInput
          value={comment}
          onChangeText={setComment}
          placeholder="댓글을 입력하세요"
          style={[ui.input, ui.grow]}
        />
        <Pressable onPress={addComment} style={ui.button}>
          <Text style={ui.buttonText}>등록</Text>
        </Pressable>
      </View>
      <View style={styles.comments}>
        {post.comments?.map((item) => (
          <View key={item.id} style={ui.card}>
            <Text style={styles.author}>
              {item.author_nickname || item.author_username}
            </Text>
            {editingId === item.id ? (
              <View style={ui.row}>
                <TextInput
                  value={editingText}
                  onChangeText={setEditingText}
                  style={[ui.input, ui.grow]}
                />
                <Pressable
                  onPress={async () => {
                    await boardsApi.updateComment(item.id, {
                      content: editingText,
                    });
                    setEditingId(null);
                    load();
                  }}
                  style={ui.buttonSecondary}
                >
                  <Text style={ui.buttonSecondaryText}>저장</Text>
                </Pressable>
              </View>
            ) : (
              <Text style={styles.comment}>{item.content}</Text>
            )}
            <View style={ui.row}>
              <Pressable
                onPress={async () => {
                  if (!requireLogin()) return;
                  try {
                    await boardsApi.likeComment(item.id);
                    void load();
                  } catch {
                    setError("댓글 좋아요를 반영하지 못했습니다.");
                  }
                }}
              >
                <Text style={styles.action}>
                  좋아요 {item.likes_count || 0}
                </Text>
              </Pressable>
              <Pressable
                onPress={async () => {
                  if (!requireLogin()) return;
                  try {
                    await boardsApi.dislikeComment(item.id);
                    void load();
                  } catch {
                    setError("댓글 싫어요를 반영하지 못했습니다.");
                  }
                }}
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
                  <Pressable
                    onPress={async () => {
                      await boardsApi.deleteComment(item.id);
                      load();
                    }}
                  >
                    <Text style={styles.deleteText}>삭제</Text>
                  </Pressable>
                </>
              ) : null}
              <Pressable
                onPress={async () => {
                  if (!requireLogin() || !reportReason.trim()) return;
                  await boardsApi.reportComment(item.id, {
                    reason: reportReason.trim(),
                  });
                  setReportReason("");
                }}
              >
                <Text style={styles.deleteText}>신고</Text>
              </Pressable>
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
                style={[ui.input, ui.grow]}
              />
              <Pressable
                onPress={async () => {
                  const content = replyDrafts[item.id]?.trim();
                  if (!requireLogin() || !content) return;
                  await boardsApi.createComment(postId, {
                    content,
                    parent: item.id,
                  });
                  setReplyDrafts((current) => ({ ...current, [item.id]: "" }));
                  load();
                }}
                style={ui.buttonSecondary}
              >
                <Text style={ui.buttonSecondaryText}>답글</Text>
              </Pressable>
            </View>
            {item.replies?.map((reply) => (
              <View key={reply.id} style={styles.reply}>
                <Text style={styles.author}>
                  {reply.author_nickname || reply.author_username}
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
  replyBox: { marginTop: 10 },
  reply: {
    marginTop: 10,
    marginLeft: 16,
    padding: 12,
    borderRadius: 10,
    backgroundColor: "#F5F7F6",
  },
  deleteText: { color: "#B42318", fontSize: 11, fontWeight: "800" },
});
