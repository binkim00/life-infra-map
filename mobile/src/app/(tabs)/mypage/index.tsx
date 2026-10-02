import { useResource } from "@/hooks/use-resource";
import { LoadState } from "@/components/load-state";
import * as ImagePicker from "expo-image-picker";
import { File } from "expo-file-system";
import { router } from "expo-router";
import { useState } from "react";
import {
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { boardsApi } from "@/api/boards";
import { ApiError, authStorage } from "@/api/client";
import { recommendationApi } from "@/api/recommendations";
import { useAuth, type AuthUser } from "@/auth/auth-context";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";
import { tierDisplay, tierColor } from "@/utils/tier-display";

type SavedPlace = {
  id: number;
  place_name?: string;
  name?: string;
  address?: string;
  memo?: string;
};
type MypageData = {
  user?: AuthUser;
  posts?: unknown[];
  comments?: unknown[];
  liked_posts?: unknown[];
};
const LINKS = [
  ["커뮤니티", "/boards/free"],
  ["새 장소 제보", "/place-report"],
  ["장소 보관함", "/mypage/saved-places"],
  ["선호 태그", "/mypage/preferences"],
  ["검색 기록", "/mypage/search-history"],
  ["장소 제보 내역", "/mypage/reports"],
  ["내 문의", "/inquiries/my"],
  ["알림", "/notifications"],
  ["설정", "/settings"],
  ["이용가이드", "/guide"],
  ["등급 안내", "/upgrade-guide"],
] as const;

export default function MypageScreen() {
  const { user, token, ready, isLoggedIn, isAdmin, logout, setUser } = useAuth();
  const [nickname, setNickname] = useState(user?.nickname || "");
  const [places, setPlaces] = useState<SavedPlace[]>([]);
  const [savedCount, setSavedCount] = useState(0);
  const [profile, setProfile] = useState<MypageData>({});
  const [memoDrafts, setMemoDrafts] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("");
  const [imageBusy, setImageBusy] = useState(false);
  const [nicknameEditing, setNicknameEditing] = useState(false);
  const load = async () => {
    const requestToken = token;
    const mypage = await boardsApi.mypage();
    if (!requestToken || (await authStorage.read()).token !== requestToken) return;
    const next = mypage as MypageData;
    setProfile(next);
    if (next.user) {
      await setUser(next.user);
      setNickname(next.user.nickname || "");
    }
    const saved = await recommendationApi.savedPlaces({ page: 1, page_size: 10 });
    if ((await authStorage.read()).token !== requestToken) return;
    const savedData = saved as { count?: number; results?: SavedPlace[] };
    setPlaces(savedData.results || []);
    setSavedCount(savedData.count ?? savedData.results?.length ?? 0);
  };
  const { loading, error: loadError, reload } = useResource(load, undefined, ready && isLoggedIn, token || "");
  const saveNickname = async () => {
    try {
      const data = (await boardsApi.updateNickname(nickname)) as {
        user?: AuthUser;
      };
      if (data.user) await setUser(data.user);
      setMessage("닉네임을 수정했습니다.");
      setNicknameEditing(false);
    } catch {
      setMessage("닉네임을 수정하지 못했습니다.");
    }
  };
  const updateImage = async () => {
    if (imageBusy) return;
    setImageBusy(true);
    setMessage("");
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setMessage("사진 접근 권한을 허용해야 프로필 사진을 바꿀 수 있습니다.");
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        quality: 0.8,
      });
      if (result.canceled) return;
      const image = result.assets[0];
      if (!image?.uri) throw new Error("선택한 사진을 읽지 못했습니다.");
      const mimeType = image.mimeType || "image/jpeg";
      const supported = new Set(["image/jpeg", "image/png", "image/gif", "image/webp"]);
      if (!supported.has(mimeType.toLowerCase())) {
        throw new Error("JPG, PNG, GIF, WebP 사진만 사용할 수 있습니다.");
      }
      const extension = mimeType.toLowerCase() === "image/jpeg"
        ? "jpg"
        : mimeType.split("/")[1];
      const originalName = image.fileName || "profile";
      const safeName = /\.(jpe?g|png|gif|webp)$/i.test(originalName)
        ? originalName
        : `${originalName}.${extension}`;
      const body = new FormData();
      body.append("profile_image", new File(image.uri), safeName);
      const data = (await boardsApi.updateProfileImage(body)) as {
        user?: AuthUser;
      };
      if (data.user) await setUser(data.user);
      setMessage("프로필 사진을 수정했습니다.");
    } catch (cause) {
      if (cause instanceof ApiError && cause.data && typeof cause.data === "object") {
        const first = Object.values(cause.data as Record<string, unknown>)[0];
        setMessage(Array.isArray(first) && first[0] ? String(first[0]) : cause.message);
      } else {
        setMessage(cause instanceof Error ? cause.message : "프로필 사진을 수정하지 못했습니다.");
      }
    } finally {
      setImageBusy(false);
    }
  };
  const saveMemo = async (id: number) => {
    try {
      await recommendationApi.updateSavedPlace(id, {
        memo: memoDrafts[id] || "",
      });
      setMessage("장소 메모를 저장했습니다.");
    } catch {
      setMessage("장소 메모를 저장하지 못했습니다.");
    }
  };
  const deletePlace = async (id: number) => {
    try {
      await recommendationApi.deleteSavedPlace(id);
      setPlaces((current) => current.filter((item) => item.id !== id));
      setSavedCount((current) => Math.max(0, current - 1));
      setMessage("저장한 장소에서 삭제했습니다.");
    } catch {
      setMessage("저장한 장소를 삭제하지 못했습니다.");
    }
  };
  const currentTier = tierDisplay(user);
  return (
    <View style={styles.root}>
      <Screen title="마이페이지" action={<Pressable accessibilityLabel="설정" onPress={() => router.push("/settings")} style={styles.settingsButton}><Text style={styles.settingsIcon}>⚙</Text></Pressable>}>
        {loading ? <LoadState loading={true} retry={reload} /> : null}
        {(
          <>
            <LoadState loading={false} error={loadError} retry={reload} />
            <View style={styles.profileCard}>
              <View style={styles.profileRow}>
                {user?.profile_image_url || user?.profile_image ? (
                  <Image
                    source={{
                      uri: user.profile_image_url || user.profile_image,
                    }}
                    style={styles.avatar}
                  />
                ) : (
                  <View style={styles.avatarPlaceholder}><Text style={styles.avatarLetter}>{(user?.nickname || user?.username || "MY").slice(0, 1)}</Text></View>
                )}
                <View style={styles.profileCopy}>
                  <Text style={[styles.nickname, { color: tierColor(user) }]}>{user?.nickname || user?.username || "여기일지도 회원"}</Text>
                  <View style={[styles.tierBadge, { backgroundColor: `${tierColor(user)}18` }]}><Text style={[styles.tierText, { color: tierColor(user) }]}>{currentTier.label}</Text></View>
                  <Text style={styles.profileTagline}>{currentTier.contribution === null ? "기여도를 확인하고 있어요." : `현재 기여도 ${currentTier.contribution}`}</Text>
                </View>
              </View>
              <View style={styles.profileActions}>
                <Pressable disabled={imageBusy} onPress={updateImage} style={styles.profileAction}><Text style={styles.profileActionText}>{imageBusy ? "사진 처리 중…" : "사진 변경"}</Text></Pressable>
                <Pressable onPress={() => setNicknameEditing((value) => !value)} style={styles.profileAction}><Text style={styles.profileActionText}>닉네임 수정</Text></Pressable>
              </View>
              {nicknameEditing ? (
                <View style={styles.nicknameEditor}>
                    <TextInput
                      value={nickname}
                      onChangeText={setNickname}
                      placeholder="닉네임"
                      placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                      style={[ui.input, ui.grow]}
                    />
                    <Pressable onPress={saveNickname} style={styles.saveNickname}>
                      <Text style={ui.buttonText}>저장</Text>
                    </Pressable>
                </View>
              ) : null}
              {message ? <Text style={styles.message}>{message}</Text> : null}
            </View>
            <View style={styles.activity}>
              <View style={styles.activityItem}><Text style={styles.count}>{savedCount}</Text><Text style={styles.activityLabel}>저장한 장소</Text></View>
              <View style={styles.activityDivider} />
              <View style={styles.activityItem}><Text style={styles.count}>{profile.posts?.length || 0}</Text><Text style={styles.activityLabel}>작성한 글</Text></View>
              <View style={styles.activityDivider} />
              <View style={styles.activityItem}><Text style={styles.count}>{profile.comments?.length || 0}</Text><Text style={styles.activityLabel}>작성한 댓글</Text></View>
            </View>
            <View style={styles.links}>
              {LINKS.map(([label, path], index) => (
                <Pressable
                  key={path}
                  onPress={() => router.push(path as never)}
                  style={styles.link}
                >
                  <Text style={styles.linkIcon}>{["☵", "⌖", "▱", "#", "⌕", "✓", "?", "♢", "⚙", "i", "↑"][index] || "•"}</Text>
                  <Text style={styles.linkText}>{label}</Text>
                  <Text style={styles.chevron}>›</Text>
                </Pressable>
              ))}
              {isAdmin ? (
                <Pressable
                  onPress={() => router.push("/admin")}
                  style={styles.link}
                >
                  <Text style={styles.linkIcon}>♢</Text><Text style={styles.adminText}>관리자 메뉴</Text>
                  <Text style={styles.chevron}>›</Text>
                </Pressable>
              ) : null}
            </View>
            <View style={styles.sectionHeading}><Text style={ui.sectionTitle}>최근 저장 장소</Text><Pressable onPress={() => router.push("/mypage/saved-places" as never)}><Text style={styles.seeAll}>전체 보기  ›</Text></Pressable></View>
            <View style={styles.list}>
              {places.length ? (
                places.slice(0, 3).map((place) => (
                  <View key={place.id} style={styles.savedCard}>
                    <View style={ui.row}>
                      <View style={ui.grow}>
                        <Pressable accessibilityRole="button" onPress={() => router.push(`/mypage/saved-places?savedId=${place.id}` as never)}>
                          <Text style={styles.placeName}>{place.place_name || place.name} · 상세보기</Text>
                        </Pressable>
                        <Text style={ui.muted}>{place.address}</Text>
                      </View>
                      <Pressable onPress={() => deletePlace(place.id)}>
                        <Text style={styles.delete}>삭제</Text>
                      </Pressable>
                    </View>
                    <View style={[ui.row, styles.memo]}>
                      <TextInput
                        value={memoDrafts[place.id] ?? place.memo ?? ""}
                        onChangeText={(value) =>
                          setMemoDrafts((current) => ({
                            ...current,
                            [place.id]: value,
                          }))
                        }
                        placeholder="장소 메모"
                        placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                        style={[ui.input, ui.grow]}
                      />
                      <Pressable
                        onPress={() => saveMemo(place.id)}
                        style={ui.buttonSecondary}
                      >
                        <Text style={ui.buttonSecondaryText}>저장</Text>
                      </Pressable>
                    </View>
                  </View>
                ))
              ) : (
                <View style={styles.emptySaved}><Text style={styles.emptyTitle}>아직 저장한 장소가 없어요</Text><Text style={ui.muted}>마음에 드는 장소를 나만의 지도에 모아보세요.</Text></View>
              )}
            </View>
            <Pressable onPress={logout} style={styles.logout}><Text style={styles.logoutText}>로그아웃</Text></Pressable>
          </>
        )}
      </Screen>
    </View>
  );
}
const styles = StyleSheet.create({
  root: { flex: 1 },
  settingsButton: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  settingsIcon: { color: Palette.ink, fontSize: 21 },
  profileCard: { padding: 18, borderWidth: 1, borderColor: Palette.border, borderRadius: Radius.large, backgroundColor: Palette.surface },
  profileRow: { flexDirection: "row", alignItems: "center", gap: 15 },
  avatar: { width: 78, height: 78, borderRadius: 39 },
  avatarPlaceholder: {
    width: 78, height: 78, alignItems: "center", justifyContent: "center", borderRadius: 39, backgroundColor: "#DCEBE7",
  },
  avatarLetter: { color: Palette.accent, fontSize: 27, fontWeight: "900" },
  profileCopy: { minWidth: 0, flex: 1, alignItems: "flex-start" },
  nickname: { color: Palette.ink, fontSize: 20, fontWeight: "900", letterSpacing: -0.5 },
  tierBadge: { marginTop: 5, paddingHorizontal: 10, paddingVertical: 4, borderRadius: Radius.pill, backgroundColor: Palette.accent },
  tierText: { color: "#FFFFFF", fontSize: 10, fontWeight: "900" },
  profileTagline: { marginTop: 7, color: Palette.muted, fontSize: 10.5 },
  profileActions: { marginTop: 15, flexDirection: "row", gap: 8 },
  profileAction: { minHeight: 38, paddingHorizontal: 14, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#B8C9C4", borderRadius: 10, backgroundColor: Palette.surface },
  profileActionText: { color: Palette.ink, fontSize: 11, fontWeight: "800" },
  nicknameEditor: { marginTop: 12, flexDirection: "row", gap: 8 },
  saveNickname: { width: 66, minHeight: 48, alignItems: "center", justifyContent: "center", borderRadius: 10, backgroundColor: Palette.accent },
  message: { marginTop: 10, color: "#0F766E", fontSize: 11 },
  links: { overflow: "hidden", borderWidth: 1, borderColor: Palette.border, borderRadius: 16, backgroundColor: "#FFFFFF" },
  link: {
    minHeight: 52,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#E3E8E5",
  },
  linkText: { flex: 1, color: "#222222", fontSize: 13, fontWeight: "800" },
  linkIcon: { width: 24, color: "#0F857A", fontSize: 16, fontWeight: "900", textAlign: "center" },
  adminText: { flex: 1, color: "#0F766E", fontSize: 13, fontWeight: "900" },
  chevron: { color: "#8A918E", fontSize: 23 },
  activity: { minHeight: 77, flexDirection: "row", alignItems: "center", borderRadius: 16, backgroundColor: Palette.accentSoft },
  activityItem: { flex: 1, alignItems: "center" },
  activityDivider: { width: 1, height: 31, backgroundColor: "#C9DFDA" },
  count: { marginBottom: 3, color: "#0F766E", fontSize: 20, fontWeight: "900" },
  activityLabel: { color: Palette.muted, fontSize: 10 },
  sectionHeading: { marginTop: 3, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  seeAll: { color: Palette.accent, fontSize: 11, fontWeight: "800" },
  list: { gap: 8 },
  savedCard: { padding: 14, borderWidth: 1, borderColor: Palette.border, borderRadius: 14, backgroundColor: Palette.surface },
  emptySaved: { padding: 22, alignItems: "center", gap: 5, borderRadius: 15, backgroundColor: Palette.surfaceMuted },
  emptyTitle: { color: Palette.ink, fontSize: 13, fontWeight: "900" },
  placeName: {
    marginBottom: 5,
    color: "#222222",
    fontSize: 14,
    fontWeight: "900",
  },
  delete: { color: "#B42318", fontSize: 11, fontWeight: "800" },
  memo: { marginTop: 10 },
  logout: { minHeight: 48, alignItems: "center", justifyContent: "center", borderRadius: 12, backgroundColor: Palette.coralSoft },
  logoutText: { color: Palette.coral, fontSize: 13, fontWeight: "900" },
});
