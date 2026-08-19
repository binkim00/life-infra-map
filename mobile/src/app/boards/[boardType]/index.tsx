import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { boardsApi } from "@/api/boards";
import { useAuth } from "@/auth/auth-context";
import { BottomNav } from "@/components/bottom-nav";
import { Screen, ui } from "@/components/screen";

type Post = {
  id: number;
  board_type: string;
  title: string;
  author_nickname?: string;
  author_username?: string;
  created_at?: string;
  comments_count?: number;
  likes_count?: number;
  view_count?: number;
  is_pinned?: boolean;
};
const LABELS: Record<string, string> = {
  free: "자유게시판",
  notice: "공지사항",
  info: "정보게시판",
};

export default function BoardListScreen() {
  const { boardType = "free" } = useLocalSearchParams<{ boardType: string }>();
  const { requireLogin } = useAuth();
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    boardsApi
      .posts(boardType)
      .then((data) => setPosts(data as Post[]))
      .catch(() => setError("게시글을 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [boardType]);
  useEffect(() => {
    void load();
  }, [load]);

  return (
    <View style={styles.root}>
      <Screen
        title={LABELS[boardType] || "게시판"}
        subtitle="정보와 경험을 나누는 공간"
        action={
          <Pressable
            onPress={() =>
              requireLogin() &&
              router.push(`/boards/${boardType}/write` as never)
            }
            style={ui.buttonSecondary}
          >
            <Text style={ui.buttonSecondaryText}>글쓰기</Text>
          </Pressable>
        }
      >
        <View style={styles.tabs}>
          {Object.entries(LABELS).map(([value, label]) => (
            <Pressable
              key={value}
              onPress={() => router.replace(`/boards/${value}` as never)}
              style={[styles.tab, boardType === value && styles.tabActive]}
            >
              <Text
                style={[
                  styles.tabText,
                  boardType === value && styles.tabTextActive,
                ]}
              >
                {label}
              </Text>
            </Pressable>
          ))}
        </View>
        {loading ? (
          <ActivityIndicator color="#0F766E" />
        ) : error ? (
          <Text style={ui.error}>{error}</Text>
        ) : (
          <View style={styles.list}>
            {posts.map((post) => (
              <Pressable
                key={post.id}
                onPress={() =>
                  router.push(`/boards/${boardType}/${post.id}` as never)
                }
                style={styles.post}
              >
                <View style={ui.grow}>
                  <Text numberOfLines={1} style={styles.title}>
                    {post.is_pinned ? "공지 · " : ""}
                    {post.title}
                  </Text>
                  <Text style={styles.meta}>
                    {post.author_nickname || post.author_username} ·{" "}
                    {post.created_at
                      ? new Date(post.created_at).toLocaleDateString()
                      : ""}
                  </Text>
                </View>
                <Text style={styles.count}>
                  댓글 {post.comments_count || 0}
                  {`\n`}좋아요 {post.likes_count || 0}
                </Text>
              </Pressable>
            ))}
          </View>
        )}
      </Screen>
      <BottomNav />
    </View>
  );
}
const styles = StyleSheet.create({
  root: { flex: 1 },
  tabs: { flexDirection: "row", gap: 7 },
  tab: {
    paddingHorizontal: 13,
    paddingVertical: 9,
    borderRadius: 999,
    backgroundColor: "#FFFFFF",
  },
  tabActive: { backgroundColor: "#222222" },
  tabText: { color: "#686159", fontSize: 11, fontWeight: "800" },
  tabTextActive: { color: "#FFFFFF" },
  list: { gap: 8 },
  post: {
    padding: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderRadius: 14,
    backgroundColor: "#FFFFFF",
  },
  title: { color: "#222222", fontSize: 14, fontWeight: "900" },
  meta: { marginTop: 6, color: "#777F7B", fontSize: 10 },
  count: { color: "#777F7B", fontSize: 9, lineHeight: 15, textAlign: "right" },
});
