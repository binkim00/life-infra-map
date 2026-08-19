import { StyleSheet, Text, View } from "react-native";

import { Palette, Radius, Shadow } from "@/constants/theme";

const MARKERS = [
  { label: "1", top: "24%", left: "23%" },
  { label: "2", top: "52%", left: "58%" },
  { label: "3", top: "32%", left: "76%" },
] as const;

export function CleanMapPreview() {
  return (
    <View
      style={styles.map}
      accessibilityLabel="일반 원형 마커가 표시된 지도 미리보기"
    >
      <View style={[styles.road, styles.roadHorizontal]} />
      <View style={[styles.road, styles.roadVertical]} />
      <View style={[styles.park, styles.parkOne]} />
      <View style={[styles.park, styles.parkTwo]} />

      {MARKERS.map((marker) => (
        <View
          key={marker.label}
          style={[styles.marker, { top: marker.top, left: marker.left }]}
          accessibilityLabel={`${marker.label}번 장소 마커`}
        >
          <Text style={styles.markerLabel}>{marker.label}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  map: {
    position: "relative",
    height: 220,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: Palette.border,
    borderRadius: Radius.large,
    backgroundColor: Palette.map,
  },
  road: {
    position: "absolute",
    backgroundColor: Palette.surface,
  },
  roadHorizontal: {
    top: "45%",
    left: -24,
    width: "120%",
    height: 28,
    transform: [{ rotate: "-7deg" }],
  },
  roadVertical: {
    top: -30,
    left: "45%",
    width: 24,
    height: "130%",
    transform: [{ rotate: "13deg" }],
  },
  park: {
    position: "absolute",
    borderRadius: Radius.large,
    backgroundColor: Palette.mapPark,
  },
  parkOne: {
    top: 20,
    right: 22,
    width: 92,
    height: 58,
  },
  parkTwo: {
    bottom: 18,
    left: 24,
    width: 116,
    height: 52,
  },
  marker: {
    position: "absolute",
    width: 34,
    height: 34,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 3,
    borderColor: Palette.surface,
    borderRadius: 17,
    backgroundColor: Palette.ink,
    boxShadow: Shadow.marker,
  },
  markerLabel: {
    color: Palette.surface,
    fontSize: 13,
    fontWeight: "800",
  },
});
