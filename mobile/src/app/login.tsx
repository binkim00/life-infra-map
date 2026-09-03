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
          <Text style={styles.brandTitle}>필요한 순간에 맞는 장소를 찾아보세요.</Text>
          <Text style={styles.brandCopy}>
            검색 기록과 선호 태그를 반영하고, 장소 저장·제보 내역을 한곳에서
            관리합니다.
          </Text>
        </View>
        <TextInput
          autoCapitalize="none"
          autoComplete="username"
          value={username}
          onChangeText={setUsername}
          placeholder="아이디"
          style={ui.input}
        />
        <TextInput
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={submit}
          placeholder="비밀번호"
          autoComplete="current-password"
          secureTextEntry
          style={ui.input}
        />
        {error ? <Text style={ui.error}>{error}</Text> : null}
        <Pressable disabled={loading} onPress={submit} style={ui.button}>
          <Text style={ui.buttonText}>
            {loading ? "로그인 중..." : "로그인"}
          </Text>
        </Pressable>
        <Pressable onPress={() => router.push("/signup")}>
          <Text style={styles.link}>계정이 없으신가요? 회원가입</Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  form: { width: "100%", maxWidth: 480, alignSelf: "center", gap: 12 },
  brandCard: {
    marginBottom: 4,
    padding: 18,
    borderWidth: 1,
    borderColor: "#D9E6E2",
    borderRadius: 18,
    backgroundColor: "#EAF6F3",
  },
  brand: {
    marginBottom: 10,
    color: "#0F766E",
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 2,
  },
  brandTitle: {
    marginBottom: 7,
    color: "#17211D",
    fontSize: 17,
    fontWeight: "900",
  },
  brandCopy: { color: "#5F6B66", fontSize: 12, lineHeight: 19 },
  link: {
    padding: 10,
    textAlign: "center",
    color: "#0F766E",
    fontSize: 13,
    fontWeight: "800",
  },
});
