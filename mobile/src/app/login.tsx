import { router, useFocusEffect } from "expo-router";
import * as Crypto from "expo-crypto";
import * as WebBrowser from "expo-web-browser";
import { useCallback, useEffect, useState } from "react";
import { BackHandler, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, apiRequest, SPRING_API } from "@/api/client";
import { useAuth } from "@/auth/auth-context";
import { Palette } from "@/constants/theme";

export default function LoginScreen() {
  const { login, exchangeSocialTicket } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [socialProviders, setSocialProviders] = useState<string[]>([]);

  const goBack = useCallback(() => {
    if (router.canGoBack()) router.back(); else router.replace("/");
  }, []);

  useFocusEffect(useCallback(() => {
    if (Platform.OS !== "android") return undefined;
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      goBack();
      return true;
    });
    return () => subscription.remove();
  }, [goBack]));

  useEffect(() => {
    let active = true;
    apiRequest<{ providers: string[] }>("/auth/social/providers", { auth: false })
      .then((data) => { if (active) setSocialProviders(data.providers || []); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const socialLogin = async (provider: string) => {
    try {
      setLoading(true);
      setError("");
      const bytes = await Crypto.getRandomBytesAsync(24);
      const nonce = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
      const callback = "lifeinframap://oauth/callback";
      const start = `${SPRING_API}/auth/social/${provider}/start?client=mobile&nonce=${nonce}`;
      const result = await WebBrowser.openAuthSessionAsync(start, callback);
      if (result.type !== "success") return;
      const url = new URL(result.url);
      if (url.protocol !== "lifeinframap:" || url.hostname !== "oauth" || url.pathname !== "/callback"
          || url.searchParams.get("nonce") !== nonce || !url.searchParams.get("ticket")) {
        throw new Error("소셜 로그인 응답을 확인하지 못했습니다.");
      }
      await exchangeSocialTicket(url.searchParams.get("ticket")!);
      if (router.canGoBack()) router.back(); else router.replace("/");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "소셜 로그인을 완료하지 못했습니다.");
    } finally { setLoading(false); }
  };

  const submit = async () => {
    if (!username || !password) return setError("아이디와 비밀번호를 입력해주세요.");
    try {
      setLoading(true);
      setError("");
      await login(username, password);
      if (router.canGoBack()) router.back(); else router.replace("/");
    } catch (caught) {
      const data = caught instanceof ApiError ? (caught.data as { detail?: string }) : null;
      setError(data?.detail || (caught instanceof Error ? caught.message : "로그인하지 못했습니다."));
    } finally { setLoading(false); }
  };

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : "height"}>
      <SafeAreaView style={styles.safe} edges={["top", "bottom", "left", "right"]}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.topBar}>
            <Pressable accessibilityLabel="뒤로 가기" onPress={goBack} style={styles.back}><Text style={styles.backText}>‹</Text></Pressable>
            <Text style={styles.language}>한국어⌄</Text>
          </View>

          <View style={styles.brandArea}>
            <View style={styles.brandMark}><View style={styles.brandMountain} /><View style={styles.brandPin}><View style={styles.brandPinDot} /></View></View>
            <Text style={styles.brandTitle}>여기일지도</Text>
            <Text style={styles.brandTagline}>아쩌면, 여기일지도</Text>
          </View>

          <View style={styles.form}>
            <View style={styles.inputWrap}><Text style={styles.inputIcon}>♙</Text><TextInput autoCapitalize="none" autoComplete="username" value={username} onChangeText={setUsername} placeholder="아이디" placeholderTextColor="#87958F" returnKeyType="next" style={styles.input} /></View>
            <View style={styles.inputWrap}>
              <Text style={styles.inputIcon}>▢</Text>
              <TextInput value={password} onChangeText={setPassword} onSubmitEditing={submit} placeholder="비밀번호" placeholderTextColor="#87958F" autoComplete="current-password" returnKeyType="done" secureTextEntry={!showPassword} style={styles.input} />
              <Pressable accessibilityLabel={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"} onPress={() => setShowPassword((value) => !value)} style={styles.passwordToggle}><Text style={styles.passwordToggleText}>{showPassword ? "●" : "◉"}</Text></Pressable>
            </View>
            {error ? <Text style={styles.error}>●  {error}</Text> : null}
            <Pressable disabled={loading} onPress={submit} style={({ pressed }) => [styles.loginButton, loading && styles.disabled, pressed && styles.pressed]}><Text style={styles.loginText}>{loading ? "로그인 중…" : "로그인"}</Text></Pressable>
            {socialProviders.length > 0 ? <Text style={styles.socialHeading}>간편 로그인</Text> : null}
            {socialProviders.length > 0 ? <View style={styles.socialRow}>{socialProviders.filter((provider) => ["google", "kakao", "naver"].includes(provider)).map((provider) => {
              const label = ({ google: "구글", kakao: "카카오", naver: "네이버" } as Record<string, string>)[provider];
              return <Pressable key={provider} accessibilityRole="button" accessibilityLabel={`${label}로 계속하기`}
                disabled={loading} onPress={() => void socialLogin(provider)}
                style={({ pressed }) => [styles.socialButton,
                  provider === "google" && styles.googleButton,
                  provider === "kakao" && styles.kakaoButton,
                  provider === "naver" && styles.naverButton,
                  loading && styles.disabled, pressed && styles.pressed]}>
                <View style={styles.socialMark}><Text style={[styles.socialMarkText,
                  provider === "google" && styles.googleMark,
                  provider === "kakao" && styles.kakaoMark,
                  provider === "naver" && styles.naverMark]}>
                  {provider === "google" ? "G" : provider === "kakao" ? "K" : "N"}
                </Text></View>
                <Text style={[styles.socialButtonText, provider === "naver" && styles.naverButtonText]}>{label}</Text>
              </Pressable>;
            })}</View> : null}
            <Pressable onPress={() => router.push("/signup")} style={styles.signupButton}><Text style={styles.signupText}>회원가입</Text></Pressable>
            <View style={styles.orRow}><View style={styles.orLine} /><Text style={styles.orText}>또는</Text><View style={styles.orLine} /></View>
            <Pressable onPress={() => router.replace("/explore")} style={styles.guestButton}><Text style={styles.guestText}>로그인 없이 둘러보기</Text></Pressable>
          </View>

          <View style={styles.footerArt}>
            <Text style={styles.footerCopy}>좋은 곳이{`\n`}당신을 기다리고 있어요.</Text>
            <View style={styles.moon} /><View style={styles.hillBack} /><View style={styles.hillFront} />
            <View style={styles.tower}><View style={styles.towerTop} /></View>
          </View>
        </ScrollView>
      </SafeAreaView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#07524B" }, safe: { flex: 1 }, content: { flexGrow: 1, minHeight: 760, paddingHorizontal: 24, paddingBottom: 0 },
  topBar: { height: 54, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, back: { width: 42, height: 42, alignItems: "center", justifyContent: "center" }, backText: { color: "#FFFFFF", fontSize: 34, fontWeight: "300" }, language: { color: "#D9ECE8", fontSize: 12, fontWeight: "700" },
  brandArea: { alignItems: "center", paddingTop: 13, paddingBottom: 31 }, brandMark: { width: 86, height: 86, position: "relative", overflow: "hidden", borderRadius: 43, backgroundColor: "#FCFAF4" }, brandMountain: { position: "absolute", left: 8, right: 8, bottom: -22, height: 70, backgroundColor: "#27867A", transform: [{ rotate: "45deg" }] }, brandPin: { position: "absolute", right: 19, top: 14, width: 31, height: 36, alignItems: "center", paddingTop: 8, borderTopLeftRadius: 16, borderTopRightRadius: 16, borderBottomLeftRadius: 16, backgroundColor: Palette.coral, transform: [{ rotate: "45deg" }] }, brandPinDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: "#FFFFFF" },
  brandTitle: { marginTop: 15, color: "#FFFFFF", fontSize: 32, fontWeight: "900", letterSpacing: -1.3 }, brandTagline: { marginTop: 4, color: "#DAECE8", fontSize: 13, letterSpacing: 2 },
  form: { width: "100%", maxWidth: 440, alignSelf: "center", gap: 11 }, inputWrap: { height: 52, paddingHorizontal: 15, flexDirection: "row", alignItems: "center", gap: 10, borderRadius: 10, backgroundColor: "#FDFDFC" }, inputIcon: { width: 21, color: "#385E58", fontSize: 19, textAlign: "center" }, input: { minWidth: 0, flex: 1, color: Palette.ink, fontSize: 14 }, passwordToggle: { width: 38, height: 38, alignItems: "center", justifyContent: "center" }, passwordToggleText: { color: "#5B746F", fontSize: 19 }, error: { color: "#FF9A87", fontSize: 11.5, fontWeight: "700" },
  loginButton: { height: 52, alignItems: "center", justifyContent: "center", borderRadius: 10, backgroundColor: Palette.coral }, loginText: { color: "#FFFFFF", fontSize: 16, fontWeight: "900" }, signupButton: { height: 36, alignItems: "center", justifyContent: "center" }, signupText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  socialHeading: { marginTop: 5, color: "#CDE7E2", fontSize: 12, fontWeight: "700", textAlign: "center" },
  socialRow: { flexDirection: "row", gap: 8 },
  socialButton: { flex: 1, minWidth: 0, height: 54, borderRadius: 10, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5 },
  googleButton: { backgroundColor: "#FFFFFF", borderColor: "#DADCE0", borderWidth: 1 },
  kakaoButton: { backgroundColor: "#FEE500" }, naverButton: { backgroundColor: "#03C75A" },
  socialMark: { width: 20, height: 20, alignItems: "center", justifyContent: "center" },
  socialMarkText: { fontSize: 16, fontWeight: "900" }, googleMark: { color: "#4285F4" },
  kakaoMark: { color: "#191919" }, naverMark: { color: "#FFFFFF" },
  socialButtonText: { color: "#222B29", fontSize: 13, fontWeight: "800" }, naverButtonText: { color: "#FFFFFF" },
  orRow: { flexDirection: "row", alignItems: "center", gap: 14 }, orLine: { height: StyleSheet.hairlineWidth, flex: 1, backgroundColor: "rgba(255,255,255,0.55)" }, orText: { color: "#D2E5E1", fontSize: 12 }, guestButton: { height: 50, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "rgba(255,255,255,0.82)", borderRadius: 12 }, guestText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  footerArt: { minHeight: 180, marginTop: 29, position: "relative", overflow: "hidden" }, footerCopy: { zIndex: 3, marginLeft: 22, color: "#FFFFFF", fontSize: 15, lineHeight: 23, fontWeight: "700", transform: [{ rotate: "-6deg" }] }, moon: { position: "absolute", right: 52, top: 13, width: 16, height: 16, borderRadius: 8, backgroundColor: "#C8E7DF" }, hillBack: { position: "absolute", left: -70, right: 80, bottom: -105, height: 220, borderRadius: 120, backgroundColor: "#4C9A90", transform: [{ rotate: "8deg" }] }, hillFront: { position: "absolute", left: 95, right: -100, bottom: -118, height: 235, borderRadius: 130, backgroundColor: "#81BDB5", transform: [{ rotate: "-8deg" }] }, tower: { position: "absolute", right: 45, bottom: 24, width: 9, height: 62, backgroundColor: "#F1F5F1" }, towerTop: { position: "absolute", left: -5, top: -10, width: 19, height: 12, borderRadius: 6, backgroundColor: "#F1F5F1" },
  disabled: { opacity: 0.55 }, pressed: { opacity: 0.72, transform: [{ scale: 0.99 }] },
});
