import { useState } from "react";
import { Linking, Pressable, Text, TextInput, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "@/components/load-state";
import { Screen, ui, INPUT_PLACEHOLDER_COLOR } from "@/components/screen";

type Evidence = {
  id: number;
  place_name: string;
  address: string;
  tag: string;
  quote: string;
  source: string;
  source_url: string;
  status: string;
  polarity: string;
  note: string;
  confidence: number;
};
const STATUSES = [
  ["pending", "확인 필요"],
  ["approved", "승인"],
  ["research", "재조사"],
  ["rejected", "반려"],
  ["all", "전체"],
] as const;
export default function EvidenceQueueScreen() {
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const action = useAction();
  const { data, loading, error, reload } = useResource(
    () =>
      recommendationApi.evidenceQueue({ status, page }) as Promise<{
        count: number;
        has_next: boolean;
        results: Evidence[];
      }>,
    { count: 0, has_next: false, results: [] as Evidence[] },
    true,
    `${status}:${page}`,
  );
  const review = (item: Evidence, decision: string) =>
    action.run(async () => {
      await recommendationApi.evidenceReview(item.id, {
        status: decision,
        note: notes[item.id] || "",
      });
      await reload();
    });
  return (
    <Screen
      title="수집 근거 검토"
      subtitle="원문과 장소·특징을 확인한 뒤 판정해 주세요. 수집 유효 판정과 관리자 승인은 다릅니다."
      back
    >
      <View style={[ui.row, { flexWrap: "wrap" }]}>
        {STATUSES.map(([value, label]) => (
          <Pressable
            key={value}
            onPress={() => {
              setStatus(value);
              setPage(1);
            }}
            style={status === value ? ui.button : ui.buttonSecondary}
          >
            <Text
              style={status === value ? ui.buttonText : ui.buttonSecondaryText}
            >
              {label}
            </Text>
          </Pressable>
        ))}
      </View>
      <LoadState
        loading={loading}
        error={error}
        empty={!data.results.length}
        retry={reload}
      />
      {!loading ? (
        <Text style={ui.muted}>
          {data.count}건 · {page}페이지
        </Text>
      ) : null}
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      {data.results.map((item) => (
        <View key={item.id} style={ui.card}>
          <Text style={ui.sectionTitle}>
            {item.place_name} · {item.tag}
          </Text>
          <Text style={ui.muted}>{item.address}</Text>
          <Text style={ui.muted}>
            {item.source} · {item.polarity} · 수집 점수 {item.confidence}
          </Text>
          <Text>{item.quote || "인용문 없음"}</Text>
          {/^https?:\/\//.test(item.source_url) ? (
            <Pressable
              onPress={() => action.run(() => Linking.openURL(item.source_url))}
              style={ui.buttonSecondary}
            >
              <Text style={ui.buttonSecondaryText}>원문 열기</Text>
            </Pressable>
          ) : null}
          {item.note ? (
            <Text style={ui.muted}>이전 검토: {item.note}</Text>
          ) : null}
          <TextInput
            value={notes[item.id] || ""}
            onChangeText={(value) =>
              setNotes((current) => ({ ...current, [item.id]: value }))
            }
            placeholder="장소 일치·인용문·조건을 확인한 판정 근거 (필수)"
            placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
            multiline
            style={ui.textarea}
          />
          <View style={ui.row}>
            {STATUSES.filter(([value]) =>
              ["approved", "rejected", "research"].includes(value),
            ).map(([value, label]) => (
              <Pressable
                key={value}
                disabled={action.busy || !notes[item.id]?.trim()}
                onPress={() => review(item, value)}
                style={ui.buttonSecondary}
              >
                <Text style={ui.buttonSecondaryText}>{label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      ))}
      <View style={ui.row}>
        <Pressable
          disabled={page === 1 || loading}
          onPress={() => setPage((p) => p - 1)}
          style={ui.buttonSecondary}
        >
          <Text>이전</Text>
        </Pressable>
        <Pressable
          disabled={!data.has_next || loading}
          onPress={() => setPage((p) => p + 1)}
          style={ui.buttonSecondary}
        >
          <Text>다음</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
