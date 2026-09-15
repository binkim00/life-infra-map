import { Image, StyleSheet, Text, View, type StyleProp, type ViewStyle } from "react-native";
import type { ReactNode } from "react";
import { AppIcon } from "@/components/app-icon";

const SPRITE = require("../../assets/images/places/place-category-sprite-v1.png");

const categoryCell = (category?: string, fallback = 0) => {
  const value = String(category || "").toLowerCase();
  if (value.includes("restaurant") || value.includes("식당") || value.includes("food")) return 1;
  if (value.includes("parking") || value.includes("주차")) return 2;
  if (value.includes("toilet") || value.includes("화장실")) return 3;
  if (value.includes("park") || value.includes("공원")) return 4;
  if (value.includes("walk") || value.includes("산책") || value.includes("shelter")) return 5;
  if (value.includes("cafe") || value.includes("카페")) return 0;
  return Math.abs(fallback) % 6;
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
  const cell = categoryCell(category, fallback);
  const column = cell % 3;
  const row = Math.floor(cell / 3);
  return (
    <View style={[styles.crop, { width, height }, style]}>
      <Image source={SPRITE} resizeMode="stretch" style={{ position: "absolute", width: width * 3, height: width * 2, left: -column * width, top: -row * width }} />
      {kakaoLinked ? <View style={styles.kakaoBadge}><AppIcon ios="map.fill" android="map" size={10} color="#FFFFFF" /><Text style={styles.kakaoText}>카카오 상세</Text></View> : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  crop: { overflow: "hidden", backgroundColor: "#DCE8E4" },
  kakaoBadge: { position: "absolute", right: 7, top: 7, flexDirection: "row", alignItems: "center", gap: 3, borderRadius: 999, backgroundColor: "rgba(15, 32, 27, 0.78)", paddingHorizontal: 7, paddingVertical: 4 },
  kakaoText: { color: "#FFFFFF", fontSize: 8, fontWeight: "900" },
});
