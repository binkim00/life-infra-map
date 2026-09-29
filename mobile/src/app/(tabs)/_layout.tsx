import { Tabs, usePathname } from "expo-router";

import { BottomNav } from "@/components/bottom-nav";

const MAIN_PATHS = new Set(["/", "/explore", "/recommend", "/saved", "/mypage", "/mypage/saved-places"]);

export default function MainTabs() {
  const pathname = usePathname();
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
