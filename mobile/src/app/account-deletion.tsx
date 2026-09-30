import { router } from "expo-router";
import { useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { apiRequest, authStorage } from "@/api/client";
import { useAuth } from "@/auth/auth-context";
import { Screen, ui } from "@/components/screen";

export default function AccountDeletionScreen() {
  const { user, isLoggedIn } = useAuth();
  const [username, setUsername] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const removeAccount = async () => {
    if (!user?.username || username !== user.username || confirmation !== "계정 삭제") {
      setError("아이디와 '계정 삭제'를 정확히 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiRequest("/account-deletion/", {
        method: "POST",
        body: { username, confirmation },
      });
      await authStorage.clear();
      router.replace("/");
    } catch {
      setError("계정을 삭제하지 못했습니다. 잠시 후 다시 시도하거나 고객 지원에 문의해 주세요.");
    } finally {
      setBusy(false);
    }
  };

  const confirmDeletion = () => Alert.alert(
    "계정을 삭제할까요?",
    "계정·저장·문의·제보 정보가 삭제됩니다. 게시글과 댓글은 작성자 표시가 익명화되고, 백업은 30일 후 만료됩니다. 이 작업은 되돌릴 수 없습니다.",
    [
      { text: "취소", style: "cancel" },
      { text: "삭제", style: "destructive", onPress: () => void removeAccount() },
    ],
  );

  return (
    <Screen title="계정 삭제" subtitle="삭제할 계정을 확인해 주세요." back>
      {!isLoggedIn ? <Text style={ui.error}>로그인 후 이용할 수 있습니다.</Text> : (
        <View style={styles.form}>
          <Text style={ui.muted}>아이디 {user?.username || ""}와 확인 문구를 입력해 주세요.</Text>
          <TextInput style={styles.input} value={username} onChangeText={setUsername}
            placeholder="아이디" autoCapitalize="none" accessibilityLabel="삭제할 계정 아이디" />
          <TextInput style={styles.input} value={confirmation} onChangeText={setConfirmation}
            placeholder="계정 삭제" accessibilityLabel="계정 삭제 확인 문구" />
          {error ? <Text style={ui.error}>{error}</Text> : null}
          <Pressable style={styles.button} disabled={busy} onPress={confirmDeletion}>
            <Text style={styles.buttonText}>{busy ? "처리 중…" : "계정 삭제하기"}</Text>
          </Pressable>
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  form: { gap: 12 },
  input: { borderWidth: 1, borderColor: "#CBD5D0", borderRadius: 10, padding: 12, backgroundColor: "#FFFFFF" },
  button: { borderRadius: 10, padding: 14, backgroundColor: "#9E3333", alignItems: "center" },
  buttonText: { color: "#FFFFFF", fontWeight: "700" },
});
