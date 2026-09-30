import { Tabs, usePathname } from "expo-router";
import { useEffect, useRef } from "react";
import { BackHandler, Platform, ToastAndroid } from "react-native";

import { BottomNav } from "@/components/bottom-nav";

const MAIN_PATHS = new Set(["/", "/explore", "/recommend", "/saved", "/mypage", "/mypage/saved-places"]);
const EXIT_PATHS = new Set(["/", "/explore", "/recommend", "/saved", "/mypage"]);

export default function MainTabs() {
  const pathname = usePathname();
  const lastBackPress = useRef(0);

  useEffect(() => {
    if (Platform.OS !== "android") return undefined;
    lastBackPress.current = 0;
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      if (!EXIT_PATHS.has(pathname)) return false;
      const now = Date.now();
      if (now - lastBackPress.current < 2000) {
        BackHandler.exitApp();
      } else {
        lastBackPress.current = now;
        ToastAndroid.show("뒤로 가기를 한 번 더 누르면 앱이 종료됩니다.", ToastAndroid.SHORT);
      }
      return true;
    });
    return () => subscription.remove();
  }, [pathname]);
  return (
    <Tabs
      screenOptions={{ headerShown: false, lazy: true, animation: "none" }}
      tabBar={() => MAIN_PATHS.has(pathname) ? <BottomNav /> : null}
    >
      <Tabs.Screen name="index" options={{ title: "홈" }} />
      <Tabs.Screen name="explore" options={{ title: "검색" }} />
      <Tabs.Screen name="recommend" options={{ title: "추천" }} />
      <Tabs.Screen name="saved" options={{ title: "저장" }} />
      <Tabs.Screen name="mypage" options={{ title: "MY" }} />
    </Tabs>
  );
}
