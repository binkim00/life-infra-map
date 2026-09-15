import { Image, StyleSheet, Text, View, type StyleProp, type ViewStyle } from "react-native";
import type { ReactNode } from "react";
import { AppIcon } from "@/components/app-icon";
import { Palette } from "@/constants/theme";

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
      {kakaoLinked ? (
        <View style={styles.kakao}><AppIcon ios="map.fill" android="map" size={Math.min(26, width * 0.28)} color={Palette.accent} /><Text style={styles.kakaoText}>KAKAO PLACE</Text></View>
      ) : (
        <Image source={SPRITE} resizeMode="stretch" style={{ position: "absolute", width: width * 3, height: width * 2, left: -column * width, top: -row * width }} />
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  crop: { overflow: "hidden", backgroundColor: "#DCE8E4" },
  kakao: { flex: 1, alignItems: "center", justifyContent: "center", gap: 5, backgroundColor: Palette.accentSoft },
  kakaoText: { color: Palette.accentDark, fontSize: 7, fontWeight: "900", letterSpacing: 0.5 },
});
