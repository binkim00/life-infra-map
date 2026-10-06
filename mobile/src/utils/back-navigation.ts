import { router } from "expo-router";
import { Alert, BackHandler, Keyboard, Platform } from "react-native";
import { nextBackAction } from "../../../shared/search-ux";

const handlers = new Map<symbol, () => boolean>();
let exitPromptOpen = false;

/** Focused screens handle overlays before navigation. Never clear search state. */
export const registerBackHandler = (handler: () => boolean) => {
  const key = Symbol("screen-back");
  handlers.set(key, handler);
  return () => { handlers.delete(key); };
};

export const handleAppBack = (pathname: string) => {
  if (Keyboard.isVisible()) { Keyboard.dismiss(); return true; }
  for (const handler of [...handlers.values()].reverse()) if (handler()) return true;
  const action = nextBackAction({ canGoBack: router.canGoBack(), root: pathname === "/" });
  if (action === "history") { router.back(); return true; }
  if (action === "home") { router.replace("/"); return true; }
  if (Platform.OS !== "android") return false;
  if (!exitPromptOpen) {
    exitPromptOpen = true;
    Alert.alert("앱 종료", "여기일지도를 종료할까요?", [
      { text: "계속 사용", style: "cancel", onPress: () => { exitPromptOpen = false; } },
      { text: "종료", onPress: () => { exitPromptOpen = false; BackHandler.exitApp(); } },
    ], { cancelable: true, onDismiss: () => { exitPromptOpen = false; } });
  }
  return true;
};
