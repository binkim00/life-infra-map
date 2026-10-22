import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Animated, PanResponder, Pressable, StyleSheet, Text, View } from "react-native";
import { Palette, Radius, Shadow } from "@/constants/theme";

export type SearchPanelLevel = "collapsed" | "peek" | "expanded";
const levels: SearchPanelLevel[] = ["collapsed", "peek", "expanded"];

export function SearchResultsPanel({ level, onLevelChange, availableHeight, expandedHeight, landscape, title, count, children }: {
  level: SearchPanelLevel;
  onLevelChange: (level: SearchPanelLevel) => void;
  availableHeight: number;
  expandedHeight: number;
  landscape: boolean;
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  const expanded = Math.max(88, expandedHeight);
  const collapsed = Math.min(88, expanded);
  const peek = Math.min(expanded, Math.max(collapsed, availableHeight * (landscape ? 0.65 : 0.34)));
  const heights = { collapsed, peek, expanded };
  const [motion] = useState(() => new Animated.Value(peek));
  const current = useRef(peek);
  const origin = useRef(peek);
  const latest = useRef({ heights, level, onLevelChange });
  useLayoutEffect(() => {
    latest.current = { heights: { collapsed, peek, expanded }, level, onLevelChange };
  }, [collapsed, peek, expanded, level, onLevelChange]);
  useEffect(() => {
    const listener = motion.addListener(({ value }) => { current.current = value; });
    return () => motion.removeListener(listener);
  }, [motion]);
  const targetHeight = heights[level];
  useEffect(() => {
    const animation = Animated.timing(motion, { toValue: targetHeight, duration: 180, useNativeDriver: false });
    animation.start();
    return () => animation.stop();
  }, [motion, targetHeight]);
  const settle = (value: number) => {
    const state = latest.current;
    const target = levels.reduce((best, candidate) =>
      Math.abs(state.heights[candidate] - value) < Math.abs(state.heights[best] - value) ? candidate : best);
    state.onLevelChange(target);
    // Also snap back after a short drag that keeps the same state.
    Animated.timing(motion, { toValue: state.heights[target], duration: 180, useNativeDriver: false }).start();
  };
  // PanResponder stores these callbacks; it does not read their refs while creating them.
  // eslint-disable-next-line react-hooks/refs
  const [pan] = useState(() => PanResponder.create({
    onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dy) > 4 && Math.abs(gesture.dy) > Math.abs(gesture.dx),
    onPanResponderGrant: () => { motion.stopAnimation(); origin.current = current.current; },
    onPanResponderMove: (_, gesture) => {
      const snap = latest.current.heights;
      motion.setValue(Math.max(snap.collapsed, Math.min(snap.expanded, origin.current - gesture.dy)));
    },
    onPanResponderRelease: (_, gesture) => settle(origin.current - gesture.dy - gesture.vy * 110),
    onPanResponderTerminate: () => settle(current.current),
  }));
  const adjust = (direction: number) => onLevelChange(levels[Math.max(0, Math.min(2, levels.indexOf(level) + direction))]);
  return (
    <Animated.View testID="search-results-panel" style={[styles.panel, landscape && styles.landscape, { height: motion }]}>
      <View {...pan.panHandlers}>
        <Pressable
          accessibilityRole="adjustable"
          accessibilityLabel="검색 결과 목록 높이"
          accessibilityValue={{ text: level === "collapsed" ? "작게" : level === "peek" ? "기본" : "크게" }}
          accessibilityActions={[{ name: "increment", label: "목록 확대" }, { name: "decrement", label: "목록 줄이기" }]}
          onAccessibilityAction={({ nativeEvent }) => adjust(nativeEvent.actionName === "increment" ? 1 : -1)}
          onPress={() => onLevelChange(level === "expanded" ? "peek" : level === "peek" ? "expanded" : "peek")}
          style={styles.gripTarget}
        ><View style={styles.grip} /></Pressable>
        <View style={styles.header}>
          <Text numberOfLines={1} style={styles.title}>{title}</Text>
          <Text style={styles.count}>{count ? `${count}곳` : ""}</Text>
          {level === "peek" ? <Pressable accessibilityRole="button" onPress={() => onLevelChange("collapsed")} hitSlop={6} style={styles.button}>
            <Text style={styles.buttonText}>지도 넓게</Text>
          </Pressable> : null}
          <Pressable accessibilityRole="button" onPress={() => onLevelChange(level === "expanded" ? "peek" : level === "collapsed" ? "peek" : "expanded")} hitSlop={6} style={styles.button}>
            <Text style={styles.buttonText}>{level === "expanded" ? "줄이기" : level === "collapsed" ? "목록 열기" : "목록 확대"}</Text>
          </Pressable>
        </View>
      </View>
      <View importantForAccessibility={level === "collapsed" ? "no-hide-descendants" : "auto"} accessibilityElementsHidden={level === "collapsed"} style={[styles.body, level === "collapsed" && styles.hidden]} pointerEvents={level === "collapsed" ? "none" : "auto"}>{children}</View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  panel: { position: "absolute", left: 12, right: 12, bottom: 8, maxWidth: 736, alignSelf: "center", paddingBottom: 8, borderWidth: 1, borderColor: "#E1E6E3", borderRadius: Radius.large, backgroundColor: "#FFF", boxShadow: Shadow.card, overflow: "hidden" },
  landscape: { left: "52%", maxWidth: undefined },
  gripTarget: { height: 28, alignItems: "center", justifyContent: "center" },
  grip: { width: 36, height: 4, borderRadius: 2, backgroundColor: "#ABB8B2" },
  header: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, minHeight: 44 },
  title: { flex: 1, fontSize: 14, fontWeight: "800", color: Palette.ink },
  count: { fontSize: 12, color: Palette.muted },
  button: { minHeight: 44, justifyContent: "center" },
  buttonText: { color: Palette.accent, fontSize: 12, fontWeight: "700" },
  body: { flex: 1, minHeight: 0 },
  hidden: { opacity: 0 },
});
