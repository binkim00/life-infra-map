import { Image, StyleSheet, Text, View, type StyleProp, type ViewStyle } from "react-native";
import type { ReactNode, ComponentProps } from "react";
import { AppIcon } from "@/components/app-icon";

const SPRITE = require("../../assets/images/places/place-category-sprite-v1.png");

const categoryCell = (category?: string) => {
  const value = String(category || "").toLowerCase();
  if (value.includes("restaurant") || value.includes("식당") || value.includes("food")) return 1;
  if (value.includes("parking") || value.includes("주차")) return 2;
  if (value.includes("toilet") || value.includes("화장실")) return 3;
  if (value.includes("park") || value.includes("공원")) return 4;
  if (value.includes("walk") || value.includes("산책") || value.includes("shelter")) return 5;
  if (value.includes("cafe") || value.includes("카페")) return 0;
  return null;
};

const categoryVisual = (category?: string): Pick<ComponentProps<typeof AppIcon>, "ios" | "android"> & { color: string } => {
  const value = String(category || "").toLowerCase();
  if (/(tour|attraction|museum|관광|문화)/.test(value)) return { ios: "building.columns", android: "museum", color: "#E9E3F5" };
  if (/(pharmacy|hospital|medical|약국|병원|의료)/.test(value)) return { ios: "cross.case", android: "local_hospital", color: "#E2F1F3" };
  if (/(shop|store|mall|쇼핑|상점)/.test(value)) return { ios: "bag", android: "shopping_bag", color: "#F6E9DD" };
  if (/(smoking|흡연)/.test(value)) return { ios: "mappin", android: "smoking_rooms", color: "#E8E9EC" };
  return { ios: "mappin", android: "place", color: "#E9F0ED" };
};

export function PlacePhoto({ category, fallback = 0, width, height, style, children, externalUrl, source }: {
  category?: string;
  fallback?: number;
  width: number;
  height: number;
  style?: StyleProp<ViewStyle>;
  children?: ReactNode;
  externalUrl?: string;
  source?: string;
}) {
  const kakaoLinked = `${externalUrl || ""} ${source || ""}`.toLowerCase().includes("kakao");
  const cell = categoryCell(category);
  const visual = categoryVisual(category);
  const column = (cell ?? 0) % 3;
  const row = Math.floor((cell ?? 0) / 3);
  return (
    <View style={[styles.crop, { width, height }, style]}>
      {cell === null ? <View style={[styles.neutral, { backgroundColor: visual.color }]}><AppIcon ios={visual.ios} android={visual.android} size={Math.min(width, height) * 0.4} color="#6E8C83" /></View> : <Image source={SPRITE} resizeMode="stretch" style={{ position: "absolute", width: width * 3, height: width * 2, left: -column * width, top: -row * height }} />}
      <View style={styles.sampleBadge}><Text style={styles.sampleText}>대표 이미지</Text></View>
      {kakaoLinked ? <View style={styles.kakaoBadge}><AppIcon ios="map.fill" android="map" size={10} color="#FFFFFF" /><Text style={styles.kakaoText}>카카오 상세</Text></View> : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  crop: { overflow: "hidden", backgroundColor: "#DCE8E4" },
  neutral: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#E9F0ED" },
  sampleBadge: { position: "absolute", left: 5, top: 5, borderRadius: 5, backgroundColor: "rgba(15,32,27,0.72)", paddingHorizontal: 5, paddingVertical: 3 },
  sampleText: { color: "#FFFFFF", fontSize: 8, fontWeight: "700" },
  kakaoBadge: { position: "absolute", right: 7, top: 7, flexDirection: "row", alignItems: "center", gap: 3, borderRadius: 999, backgroundColor: "rgba(15, 32, 27, 0.78)", paddingHorizontal: 7, paddingVertical: 4 },
  kakaoText: { color: "#FFFFFF", fontSize: 8, fontWeight: "900" },
});
