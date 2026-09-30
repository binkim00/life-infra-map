import * as ImagePicker from "expo-image-picker";
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

import { useAuth } from "@/auth/auth-context";
import { ApiError } from "@/api/client";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";

export default function SignupScreen() {
  const { signup } = useAuth();
  const [form, setForm] = useState({
    username: "",
    nickname: "",
    email: "",
    password: "",
    passwordConfirm: "",
  });
  const [image, setImage] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const field = (key: keyof typeof form, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const pickImage = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError("프로필 사진을 선택하려면 사진 접근 권한을 허용해 주세요.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.8,
    });
    if (!result.canceled) setImage(result.assets[0]);
  };

  const submit = async () => {
    if (!form.username || !form.nickname || !form.password)
      return setError("아이디, 닉네임, 비밀번호를 입력해주세요.");
    if (form.password !== form.passwordConfirm)
      return setError("비밀번호가 일치하지 않습니다.");
    let body: FormData | Record<string, string> = {
      username: form.username,
      nickname: form.nickname,
      email: form.email,
      password: form.password,
      password_confirm: form.passwordConfirm,
    };
    if (image) {
      body = new FormData();
      body.append("username", form.username);
      body.append("nickname", form.nickname);
      body.append("email", form.email);
      body.append("password", form.password);
      body.append("password_confirm", form.passwordConfirm);
      body.append("profile_image", {
        uri: image.uri,
        name: image.fileName || "profile.jpg",
        type: image.mimeType || "image/jpeg",
      } as unknown as Blob);
    }
    try {
      setLoading(true);
      setError("");
      await signup(body);
      router.replace("/");
    } catch (cause) {
      if (cause instanceof ApiError && cause.data && typeof cause.data === "object") {
        const first = Object.values(cause.data as Record<string, unknown>)[0];
        setError(Array.isArray(first) && first[0] ? String(first[0]) : cause.message);
      } else {
        setError(cause instanceof Error ? cause.message : "회원가입에 실패했습니다. 입력 내용을 확인해 주세요.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Screen title="회원가입" subtitle="여기일지도를 시작합니다." back>
      <View style={styles.form}>
        <Pressable onPress={pickImage} style={styles.picker}>
          {image ? (
            <Image source={{ uri: image.uri }} style={styles.avatar} />
          ) : (
            <View style={styles.avatarPlaceholder} />
          )}
          <Text style={styles.pickText}>프로필 사진 선택</Text>
        </Pressable>
        <TextInput
          autoCapitalize="none"
          value={form.username}
          onChangeText={(v) => field("username", v)}
          placeholder="아이디"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={ui.input}
        />
        <TextInput
          value={form.nickname}
          onChangeText={(v) => field("nickname", v)}
          placeholder="닉네임"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={ui.input}
        />
        <TextInput
          keyboardType="email-address"
          autoCapitalize="none"
          value={form.email}
          onChangeText={(v) => field("email", v)}
          placeholder="이메일 (선택)"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={ui.input}
        />
        <View style={styles.passwordRow}>
          <TextInput
            value={form.password}
            onChangeText={(v) => field("password", v)}
            placeholder="비밀번호"
            placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
            secureTextEntry={!showPassword}
            style={[ui.input, styles.passwordInput]}
          />
          <Pressable accessibilityRole="button" onPress={() => setShowPassword((value) => !value)} style={styles.passwordToggle}>
            <Text style={styles.passwordToggleText}>{showPassword ? "숨김" : "보기"}</Text>
          </Pressable>
        </View>
        <TextInput
          value={form.passwordConfirm}
          onChangeText={(v) => field("passwordConfirm", v)}
          onSubmitEditing={submit}
          placeholder="비밀번호 확인"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          secureTextEntry={!showPassword}
          returnKeyType="done"
          style={ui.input}
        />
        {error ? <Text style={ui.error}>{error}</Text> : null}
        <Pressable disabled={loading} onPress={submit} style={[ui.button, loading && styles.disabled]}>
          <Text style={ui.buttonText}>
            {loading ? "처리 중..." : "가입하기"}
          </Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  form: { width: "100%", maxWidth: 480, alignSelf: "center", gap: 12 },
  picker: { alignItems: "center", gap: 8, marginBottom: 8 },
  avatar: { width: 76, height: 76, borderRadius: 38 },
  avatarPlaceholder: {
    width: 76,
    height: 76,
    borderRadius: 38,
    backgroundColor: "#DCE7E2",
  },
  pickText: { color: "#0F766E", fontSize: 12, fontWeight: "800" },
  passwordRow: { position: "relative", justifyContent: "center" },
  passwordInput: { paddingRight: 64 },
  passwordToggle: { position: "absolute", right: 8, minWidth: 48, minHeight: 38, alignItems: "center", justifyContent: "center" },
  passwordToggleText: { color: "#0F857A", fontSize: 12, fontWeight: "900" },
  disabled: { opacity: 0.55 },
});
