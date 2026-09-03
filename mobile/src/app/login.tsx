import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/auth-context";
import { Screen, ui } from "@/components/screen";

export default function LoginScreen() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!username || !password)
      return setError("아이디와 비밀번호를 입력해주세요.");
    try {
      setLoading(true);
      setError("");
      await login(username, password);
      router.replace("/");
    } catch (caught) {
      const data =
        caught instanceof ApiError
          ? (caught.data as { detail?: string })
          : null;
      setError(data?.detail || "아이디 또는 비밀번호가 올바르지 않습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Screen
      title="로그인"
      subtitle="저장한 장소와 개인화 추천을 이용하세요."
      back
    >
      <View style={styles.form}>
        <View style={styles.brandCard}>
          <Text style={styles.brand}>LIFE MAP</Text>
          <Text style={styles.brandTitle}>
            지금 필요한 장소를{`\n`}더 쉽게 찾아보세요.
          </Text>
          <Text style={styles.brandCopy}>
            내 취향에 맞는 추천을 받고, 마음에 드는 장소를 저장할 수 있어요.
          </Text>
          <View style={styles.benefits}>
            <Text style={styles.benefit}>상황 맞춤 추천</Text>
            <Text style={styles.benefit}>장소 저장</Text>
            <Text style={styles.benefit}>제보 관리</Text>
          </View>
        </View>
        <View style={styles.loginCard}>
          <View>
            <Text style={styles.fieldLabel}>아이디</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete="username"
              value={username}
              onChangeText={setUsername}
              placeholder="아이디를 입력하세요"
              placeholderTextColor="#8A918E"
              returnKeyType="next"
              style={ui.input}
            />
          </View>
          <View>
            <Text style={styles.fieldLabel}>비밀번호</Text>
            <TextInput
              value={password}
              onChangeText={setPassword}
              onSubmitEditing={submit}
              placeholder="비밀번호를 입력하세요"
              placeholderTextColor="#8A918E"
              autoComplete="current-password"
              returnKeyType="done"
              secureTextEntry
              style={ui.input}
            />
          </View>
          {error ? <Text style={ui.error}>{error}</Text> : null}
          <Pressable
            disabled={loading}
            onPress={submit}
            style={[ui.button, loading && styles.buttonDisabled]}
          >
            <Text style={ui.buttonText}>
              {loading ? "로그인 중..." : "로그인"}
            </Text>
          </Pressable>
          <Pressable onPress={() => router.push("/signup")}>
            <Text style={styles.link}>계정이 없으신가요? 회원가입</Text>
          </Pressable>
        </View>
        <Pressable
          onPress={() => router.replace("/explore")}
          style={styles.guestButton}
        >
          <Text style={styles.guestButtonText}>로그인 없이 둘러보기</Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  form: { width: "100%", maxWidth: 480, alignSelf: "center", gap: 14 },
  brandCard: {
    padding: 22,
    borderRadius: 22,
    backgroundColor: "#123D38",
  },
  brand: {
    marginBottom: 14,
    color: "#8DE0D2",
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 2,
  },
  brandTitle: {
    marginBottom: 9,
    color: "#FFFFFF",
    fontSize: 23,
    fontWeight: "900",
    lineHeight: 31,
  },
  brandCopy: { color: "#D1E7E2", fontSize: 13, lineHeight: 20 },
  benefits: {
    marginTop: 16,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 7,
  },
  benefit: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(255, 255, 255, 0.12)",
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "700",
  },
  loginCard: {
    gap: 14,
    padding: 18,
    borderWidth: 1,
    borderColor: "#E2E7E4",
    borderRadius: 20,
    backgroundColor: "#FFFFFF",
  },
  fieldLabel: {
    marginBottom: 8,
    color: "#27312D",
    fontSize: 13,
    fontWeight: "800",
  },
  buttonDisabled: { opacity: 0.55 },
  link: {
    paddingTop: 2,
    paddingBottom: 1,
    textAlign: "center",
    color: "#0F766E",
    fontSize: 13,
    fontWeight: "800",
  },
  guestButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#C8D3CF",
    borderRadius: 12,
    backgroundColor: "#F5F7F6",
  },
  guestButtonText: { color: "#39443F", fontSize: 13, fontWeight: "800" },
});
