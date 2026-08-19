import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
type Report = {
  id: number;
  place_name?: string;
  suggested_name?: string;
  report_type?: string;
  status?: string;
  description?: string;
  suggested_tags?: string[];
};
export default function AdminPlaceReportsScreen() {
  const [items, setItems] = useState<Report[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const load = () =>
    recommendationApi
      .adminPlaceReports({ page: 1, page_size: 50 })
      .then((data) => setItems((data.results || []) as Report[]))
      .catch(() => setError("장소 제보 목록을 불러오지 못했습니다."));
  useEffect(() => {
    void load();
  }, []);
  const review = async (item: Report, approve: boolean) => {
    const body = { admin_note: notes[item.id] || "" };
    if (approve) await recommendationApi.approvePlaceReport(item.id, body);
    else await recommendationApi.rejectPlaceReport(item.id, body);
    load();
  };
  return (
    <Screen
      title="장소 제보 검토"
      subtitle="승인 시 검색 데이터와 기여도에 반영됩니다."
      back
    >
      {error ? <Text style={ui.error}>{error}</Text> : null}
      <View style={styles.list}>
        {items.map((item) => (
          <View key={item.id} style={ui.card}>
            <View style={ui.row}>
              <Text style={styles.title}>
                {item.suggested_name || item.place_name || `제보 #${item.id}`}
              </Text>
              <Text style={styles.status}>{item.status}</Text>
            </View>
            <Text style={ui.muted}>{item.report_type}</Text>
            <Text style={styles.description}>{item.description}</Text>
            {item.suggested_tags?.length ? (
              <Text style={ui.muted}>{item.suggested_tags.join(" · ")}</Text>
            ) : null}
            <TextInput
              value={notes[item.id] || ""}
              onChangeText={(value) =>
                setNotes((current) => ({ ...current, [item.id]: value }))
              }
              placeholder="검토 메모"
              style={ui.input}
            />
            <View style={ui.row}>
              <Pressable onPress={() => review(item, true)} style={ui.button}>
                <Text style={ui.buttonText}>승인</Text>
              </Pressable>
              <Pressable
                onPress={() => review(item, false)}
                style={ui.buttonSecondary}
              >
                <Text style={styles.reject}>반려</Text>
              </Pressable>
            </View>
          </View>
        ))}
      </View>
    </Screen>
  );
}
const styles = StyleSheet.create({
  list: { gap: 8 },
  title: { flex: 1, color: "#222222", fontSize: 14, fontWeight: "900" },
  status: { color: "#0F766E", fontSize: 10, fontWeight: "800" },
  description: {
    marginVertical: 10,
    color: "#38403C",
    fontSize: 12,
    lineHeight: 19,
  },
  reject: { color: "#B42318", fontSize: 12, fontWeight: "900" },
});
