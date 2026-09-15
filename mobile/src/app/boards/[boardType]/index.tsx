import { useMemo, useState } from "react";
import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import { router, useLocalSearchParams } from "expo-router";

import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { boardsApi } from "@/api/boards";
import { useAuth } from "@/auth/auth-context";
import { BottomNav } from "@/components/bottom-nav";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";

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
  const [query, setQuery] = useState("");
  const { requireLogin } = useAuth();
  const { data: posts, loading, error, reload: load } = useResource<Post[]>(
    () => boardsApi.posts(boardType).then(data => data as Post[]), [], true, boardType,
  );
  const visiblePosts = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return posts;
    return posts.filter((post) => `${post.title} ${post.author_nickname || post.author_username || ""}`.toLowerCase().includes(keyword));
  }, [posts, query]);
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
        <View style={styles.communityHero}>
          <Text style={styles.heroEyebrow}>LIFEMAP COMMUNITY</Text>
          <Text style={styles.heroTitle}>동네의 진짜 정보를{`\n`}함께 나눠요</Text>
          <Text style={styles.heroCopy}>장소 팁부터 새로운 소식까지, 필요한 이야기를 빠르게 찾아보세요.</Text>
        </View>
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
        <View style={styles.searchBox}>
          <Text style={styles.searchIcon}>⌕</Text>
          <TextInput value={query} onChangeText={setQuery} placeholder="제목이나 작성자 검색" placeholderTextColor={INPUT_PLACEHOLDER_COLOR} style={styles.searchInput} />
          {query ? <Pressable onPress={() => setQuery("")}><Text style={styles.clear}>×</Text></Pressable> : null}
        </View>
        {loading ? (
          <LoadState loading={loading} retry={load} />
        ) : error ? (
          <LoadState loading={false} error={error} retry={load} />
        ) : (
          <View style={styles.list}>
            <LoadState loading={false} empty={!visiblePosts.length} retry={load} emptyText={query ? "검색 결과가 없습니다." : "아직 게시글이 없습니다."} />
            {visiblePosts.map((post) => (
              <Pressable
                key={post.id}
                onPress={() =>
                  router.push(`/boards/${boardType}/${post.id}` as never)
                }
                style={styles.post}
              >
                <View style={ui.grow}>
                  {post.is_pinned ? <Text style={styles.pinned}>공지사항</Text> : null}
                  <Text numberOfLines={1} style={styles.title}>
                    {post.title}
                  </Text>
                  <Text style={styles.meta}>
                    {post.author_nickname || post.author_username} ·{" "}
                    {post.created_at
                      ? new Date(post.created_at).toLocaleDateString()
                      : ""}
                  </Text>
                </View>
                <View style={styles.metrics}><Text style={styles.count}>♡ {post.likes_count || 0}</Text><Text style={styles.count}>◯ {post.comments_count || 0}</Text><Text style={styles.chevron}>›</Text></View>
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
  communityHero: { padding: 20, borderRadius: Radius.large, backgroundColor: Palette.ink },
  heroEyebrow: { color: "#70D4C9", fontSize: 9, fontWeight: "900", letterSpacing: 1.4 },
  heroTitle: { marginTop: 8, color: "#FFFFFF", fontSize: 22, lineHeight: 29, fontWeight: "900", letterSpacing: -0.5 },
  heroCopy: { marginTop: 10, maxWidth: 290, color: "#BDC8C3", fontSize: 11, lineHeight: 18 },
  tabs: { padding: 4, flexDirection: "row", gap: 4, borderRadius: Radius.medium, backgroundColor: Palette.surfaceMuted },
  tab: {
    flex: 1,
    alignItems: "center",
    paddingHorizontal: 8,
    paddingVertical: 10,
    borderRadius: 12,
  },
  tabActive: { backgroundColor: Palette.surface },
  tabText: { color: "#686159", fontSize: 11, fontWeight: "800" },
  tabTextActive: { color: Palette.ink },
  searchBox: { minHeight: 48, paddingHorizontal: 14, flexDirection: "row", alignItems: "center", gap: 10, borderWidth: 1, borderColor: Palette.border, borderRadius: Radius.medium, backgroundColor: Palette.surface },
  searchIcon: { color: Palette.accent, fontSize: 21, fontWeight: "900" },
  searchInput: { minWidth: 0, flex: 1, color: Palette.ink, fontSize: 13 },
  clear: { color: Palette.muted, fontSize: 22 },
  list: { gap: 8 },
  post: {
    padding: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: Palette.border,
    borderRadius: Radius.medium,
    backgroundColor: "#FFFFFF",
  },
  title: { color: "#222222", fontSize: 14, fontWeight: "900" },
  pinned: { marginBottom: 5, color: Palette.coral, fontSize: 9, fontWeight: "900" },
  meta: { marginTop: 6, color: "#777F7B", fontSize: 10 },
  metrics: { alignItems: "flex-end", gap: 3 },
  count: { color: "#777F7B", fontSize: 9, lineHeight: 13, textAlign: "right" },
  chevron: { marginTop: 3, color: Palette.accent, fontSize: 20, fontWeight: "700" },
});
