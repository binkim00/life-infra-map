import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { Screen, ui, INPUT_PLACEHOLDER_COLOR } from "@/components/screen";
import { Palette, Radius } from "@/constants/theme";

const CATEGORIES = [
  { label: "카페", code: "cafe" }, { label: "식당", code: "restaurant" },
  { label: "공원", code: "city_park" }, { label: "주차장", code: "parking" },
  { label: "화장실", code: "toilet" }, { label: "쉼터", code: "shelter" },
];
const SITUATIONS = ["혼자 이용", "가족과 함께", "데이트", "작업·공부", "잠깐 쉬기"];
const CONDITIONS = [
  { label: "주차 가능", code: "parking" }, { label: "콘센트 있음", code: "outlet" },
  { label: "조용함", code: "quiet" }, { label: "반려동물 동반", code: "pet" },
  { label: "유아 의자 있음", code: "high_chair" },
];

export default function FilterSearchScreen() {
  const [location, setLocation] = useState("");
  const [category, setCategory] = useState("");
  const [situation, setSituation] = useState("");
  const [required, setRequired] = useState<string[]>([]);
  const [error, setError] = useState("");
  const toggle = (value: string) => setRequired((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  const search = () => {
    if (!location.trim() || !category) {
      setError("지역과 장소 종류를 선택해 주세요.");
      return;
    }
    const categoryLabel = CATEGORIES.find((item) => item.code === category)?.label || "장소";
    const requirementLabels = required.map((code) => CONDITIONS.find((item) => item.code === code)?.label).filter(Boolean);
    const query = `${location.trim()}에서 ${situation ? `${situation} ` : ""}${categoryLabel} 추천해줘${requirementLabels.length ? `. ${requirementLabels.join(", ")} 필수` : ""}`;
    router.push({ pathname: "/recommend", params: {
      q: query,
      searchRequest: String(Date.now()),
      selectedFilters: JSON.stringify({ location: location.trim(), category, required }),
    } });
  };
  return <Screen title="조건 골라 찾기" subtitle="지역과 원하는 조건을 고르면 근거를 확인해 장소를 추천합니다." back>
    <Text style={ui.label}>지역</Text>
    <TextInput value={location} onChangeText={setLocation} placeholder="예: 서면, 해운대" placeholderTextColor={INPUT_PLACEHOLDER_COLOR} style={ui.input} />
    <Text style={ui.label}>장소 종류</Text>
    <View style={styles.options}>{CATEGORIES.map((item) => <Pressable key={item.code} onPress={() => setCategory(item.code)} style={[styles.option, category === item.code && styles.selected]}><Text style={category === item.code ? styles.selectedText : styles.optionText}>{item.label}</Text></Pressable>)}</View>
    <Text style={ui.label}>상황 (선택)</Text>
    <View style={styles.options}>{SITUATIONS.map((value) => <Pressable key={value} onPress={() => setSituation(situation === value ? "" : value)} style={[styles.option, situation === value && styles.selected]}><Text style={situation === value ? styles.selectedText : styles.optionText}>{value}</Text></Pressable>)}</View>
    <Text style={ui.label}>꼭 필요한 조건 (여러 개 선택 가능)</Text>
    <View style={styles.options}>{CONDITIONS.map((item) => <Pressable key={item.code} onPress={() => toggle(item.code)} style={[styles.option, required.includes(item.code) && styles.selected]}><Text style={required.includes(item.code) ? styles.selectedText : styles.optionText}>{item.label}</Text></Pressable>)}</View>
    <Text style={ui.muted}>선택한 필수 조건을 직접 확인할 근거가 부족하면 추천 화면에서 ‘확인 필요’로 안내합니다.</Text>
    {error ? <Text style={ui.error}>{error}</Text> : null}
    <Pressable onPress={search} style={ui.button}><Text style={ui.buttonText}>선택 조건으로 찾기</Text></Pressable>
  </Screen>;
}

const styles = StyleSheet.create({
  options: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginBottom: 12 },
  option: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: Radius.pill, backgroundColor: Palette.surfaceMuted },
  selected: { backgroundColor: Palette.ink },
  optionText: { color: Palette.ink, fontWeight: "700" },
  selectedText: { color: "#FFFFFF", fontWeight: "700" },
});
