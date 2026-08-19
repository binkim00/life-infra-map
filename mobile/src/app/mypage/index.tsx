import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";
import { useEffect, useState } from "react";
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
import { recommendationApi } from "@/api/recommendations";
import { useAuth, type AuthUser } from "@/auth/auth-context";
import { BottomNav } from "@/components/bottom-nav";
import { Screen, ui } from "@/components/screen";

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
  ["선호 태그", "/mypage/preferences"],
  ["검색 기록", "/mypage/search-history"],
  ["장소 제보 내역", "/mypage/reports"],
  ["내 문의", "/inquiries/my"],
  ["알림", "/notifications"],
  ["설정", "/settings"],
  ["이용가이드", "/guide"],
  ["승급가이드", "/upgrade-guide"],
] as const;

export default function MypageScreen() {
  const { user, isLoggedIn, isAdmin, logout, setUser } = useAuth();
  const [nickname, setNickname] = useState(user?.nickname || "");
  const [places, setPlaces] = useState<SavedPlace[]>([]);
  const [profile, setProfile] = useState<MypageData>({});
  const [memoDrafts, setMemoDrafts] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const load = async () => {
    const [mypage, saved] = await Promise.all([
      boardsApi.mypage(),
      recommendationApi.savedPlaces({ page: 1, page_size: 10 }),
    ]);
    const next = mypage as MypageData;
    setProfile(next);
    if (next.user) {
      await setUser(next.user);
      setNickname(next.user.nickname || "");
    }
    setPlaces((saved as { results?: SavedPlace[] }).results || []);
  };
  useEffect(() => {
    if (!isLoggedIn) {
      router.replace("/login");
      return;
    }
    void Promise.resolve()
      .then(load)
      .catch(() => setMessage("마이페이지 정보를 불러오지 못했습니다."))
      .finally(() =>
        setLoading(false),
      ); /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [isLoggedIn]);
  const saveNickname = async () => {
    try {
      const data = (await boardsApi.updateNickname(nickname)) as {
        user?: AuthUser;
      };
      if (data.user) await setUser(data.user);
      setMessage("닉네임을 수정했습니다.");
    } catch {
      setMessage("닉네임을 수정하지 못했습니다.");
    }
  };
  const updateImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.8,
    });
    if (result.canceled) return;
    const image = result.assets[0];
    const body = new FormData();
    body.append("profile_image", {
      uri: image.uri,
      name: image.fileName || "profile.jpg",
      type: image.mimeType || "image/jpeg",
    } as unknown as Blob);
    const data = (await boardsApi.updateProfileImage(body)) as {
      user?: AuthUser;
    };
    if (data.user) await setUser(data.user);
    setMessage("프로필 사진을 수정했습니다.");
  };
  const saveMemo = async (id: number) => {
    await recommendationApi.updateSavedPlace(id, {
      memo: memoDrafts[id] || "",
    });
    setMessage("장소 메모를 저장했습니다.");
  };
  const deletePlace = async (id: number) => {
    await recommendationApi.deleteSavedPlace(id);
    setPlaces((current) => current.filter((item) => item.id !== id));
  };
  return (
    <View style={styles.root}>
      <Screen
        title="마이페이지"
        subtitle={user?.username || ""}
        action={
          <Pressable onPress={logout} style={ui.buttonSecondary}>
            <Text style={ui.buttonSecondaryText}>로그아웃</Text>
          </Pressable>
        }
      >
        {loading ? (
          <ActivityIndicator color="#0F766E" />
        ) : (
          <>
            <View style={ui.card}>
              <View style={styles.profileRow}>
                {user?.profile_image_url || user?.profile_image ? (
                  <Image
                    source={{
                      uri: user.profile_image_url || user.profile_image,
                    }}
                    style={styles.avatar}
                  />
                ) : (
                  <View style={styles.avatarPlaceholder} />
                )}
                <View style={ui.grow}>
                  <Text style={ui.label}>닉네임</Text>
                  <View style={ui.row}>
                    <TextInput
                      value={nickname}
                      onChangeText={setNickname}
                      style={[ui.input, ui.grow]}
                    />
                    <Pressable onPress={saveNickname} style={ui.button}>
                      <Text style={ui.buttonText}>저장</Text>
                    </Pressable>
                  </View>
                </View>
              </View>
              <Pressable onPress={updateImage} style={styles.imageButton}>
                <Text style={styles.imageButtonText}>프로필 사진 변경</Text>
              </Pressable>
              {message ? <Text style={styles.message}>{message}</Text> : null}
            </View>
            <View style={styles.links}>
              {LINKS.map(([label, path]) => (
                <Pressable
                  key={path}
                  onPress={() => router.push(path)}
                  style={styles.link}
                >
                  <Text style={styles.linkText}>{label}</Text>
                  <Text style={styles.chevron}>›</Text>
                </Pressable>
              ))}
              {isAdmin ? (
                <Pressable
                  onPress={() => router.push("/admin")}
                  style={styles.link}
                >
                  <Text style={styles.adminText}>관리자 메뉴</Text>
                  <Text style={styles.chevron}>›</Text>
                </Pressable>
              ) : null}
            </View>
            <View style={styles.activity}>
              <View style={ui.card}>
                <Text style={styles.count}>{profile.posts?.length || 0}</Text>
                <Text style={ui.muted}>작성한 글</Text>
              </View>
              <View style={ui.card}>
                <Text style={styles.count}>
                  {profile.comments?.length || 0}
                </Text>
                <Text style={ui.muted}>작성한 댓글</Text>
              </View>
              <View style={ui.card}>
                <Text style={styles.count}>
                  {profile.liked_posts?.length || 0}
                </Text>
                <Text style={ui.muted}>좋아요한 글</Text>
              </View>
            </View>
            <Text style={ui.sectionTitle}>저장한 장소 {places.length}</Text>
            <View style={styles.list}>
              {places.length ? (
                places.map((place) => (
                  <View key={place.id} style={ui.card}>
                    <View style={ui.row}>
                      <View style={ui.grow}>
                        <Text style={styles.placeName}>
                          {place.place_name || place.name}
                        </Text>
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
                <Text style={ui.muted}>아직 저장한 장소가 없습니다.</Text>
              )}
            </View>
          </>
        )}
      </Screen>
      <BottomNav />
    </View>
  );
}
const styles = StyleSheet.create({
  root: { flex: 1 },
  profileRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  avatar: { width: 60, height: 60, borderRadius: 30 },
  avatarPlaceholder: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: "#DCE7E2",
  },
  imageButton: { marginTop: 10 },
  imageButtonText: { color: "#0F766E", fontSize: 11, fontWeight: "800" },
  message: { marginTop: 10, color: "#0F766E", fontSize: 11 },
  links: { overflow: "hidden", borderRadius: 16, backgroundColor: "#FFFFFF" },
  link: {
    minHeight: 54,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#E3E8E5",
  },
  linkText: { flex: 1, color: "#222222", fontSize: 13, fontWeight: "800" },
  adminText: { flex: 1, color: "#0F766E", fontSize: 13, fontWeight: "900" },
  chevron: { color: "#8A918E", fontSize: 23 },
  activity: { flexDirection: "row", gap: 8 },
  count: { marginBottom: 5, color: "#0F766E", fontSize: 22, fontWeight: "900" },
  list: { gap: 8 },
  placeName: {
    marginBottom: 5,
    color: "#222222",
    fontSize: 14,
    fontWeight: "900",
  },
  delete: { color: "#B42318", fontSize: 11, fontWeight: "800" },
  memo: { marginTop: 10 },
});
