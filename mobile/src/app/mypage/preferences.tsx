import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";

type Tag = {
  id: number;
  name?: string;
  label?: string;
  display_name?: string;
  group?: string;
};
type Preference = {
  id: number;
  key?: string;
  label?: string;
  source?: string;
  preference_type?: string;
};

export default function PreferencesScreen() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [message, setMessage] = useState("");
  const load = useCallback(
    () =>
      Promise.all([
        recommendationApi.preferenceTags(),
        recommendationApi.preferences({ page: 1, page_size: 100 }),
      ])
        .then(([tagData, prefData]) => {
          const tagResults = Array.isArray(tagData)
            ? tagData
            : (tagData as { results?: Tag[] }).results;
          setTags(Array.isArray(tagResults) ? (tagResults as Tag[]) : []);
          setPreferences(
            (prefData as { results?: Preference[] }).results || [],
          );
        })
        .catch(() => setMessage("선호 정보를 불러오지 못했습니다.")),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);
  const selected = useMemo(
    () =>
      new Map(
        preferences
          .filter(
            (item) =>
              item.source === "direct" || item.preference_type === "tag",
          )
          .map((item) => [
            String(item.key || item.label || "").toLowerCase(),
            item,
          ]),
      ),
    [preferences],
  );
  const groups = useMemo(() => {
    const map = new Map<string, Tag[]>();
    tags.forEach((tag) => {
      const key = tag.group || "기타";
      map.set(key, [...(map.get(key) || []), tag]);
    });
    return [...map.entries()];
  }, [tags]);
  const toggle = async (tag: Tag) => {
    const key = String(tag.name || tag.label || "").toLowerCase();
    const current = selected.get(key);
    try {
      if (current) await recommendationApi.deletePreference(current.id);
      else
        await recommendationApi.createPreference({
          preference_type: "tag",
          tag_id: tag.id,
        });
      setMessage(
        current ? "선택을 해제했습니다." : "선호 태그를 저장했습니다.",
      );
      load();
    } catch {
      setMessage("선호 태그를 저장하지 못했습니다.");
    }
  };
  return (
    <Screen
      title="선호 태그"
      subtitle="추천에 더 반영할 조건을 선택하세요."
      back
    >
      {message ? <Text style={ui.success}>{message}</Text> : null}
      {groups.map(([group, groupTags]) => (
        <View key={group} style={ui.card}>
          <Text style={styles.group}>{group}</Text>
          <View style={styles.tags}>
            {groupTags.map((tag) => {
              const active = selected.has(
                String(tag.name || tag.label || "").toLowerCase(),
              );
              return (
                <Pressable
                  key={tag.id}
                  onPress={() => toggle(tag)}
                  style={[styles.tag, active && styles.tagActive]}
                >
                  <Text
                    style={[styles.tagText, active && styles.tagTextActive]}
                  >
                    {tag.display_name || tag.name || tag.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ))}
      <View style={ui.card}>
        <Text style={styles.group}>검색 기반 자동 선호</Text>
        {preferences
          .filter((item) => item.source !== "direct")
          .map((item) => (
            <Text key={item.id} style={ui.muted}>
              • {item.label || item.key}
            </Text>
          ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  group: {
    marginBottom: 12,
    color: "#222222",
    fontSize: 14,
    fontWeight: "900",
  },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  tag: {
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderWidth: 1,
    borderColor: "#DCE3DF",
    borderRadius: 999,
  },
  tagActive: { borderColor: "#0F766E", backgroundColor: "#E6F4F1" },
  tagText: { color: "#686159", fontSize: 11, fontWeight: "800" },
  tagTextActive: { color: "#0F766E" },
});
