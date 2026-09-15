import { useState } from "react";
import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { apiRequest } from "@/api/client";
import { Screen, ui } from "@/components/screen";
import { LoadState } from "@/components/load-state";
import { useResource } from "@/hooks/use-resource";
import { Palette, Radius } from "@/constants/theme";

type Judgment = { place_name: string; tag: string; status: string; reason: string };
type Run = { id: number; run_key: string; payload: { rows?: number; accepted?: number; needs_verification?: number; rejected?: number; duplicate?: number; saved?: number; reasons?: Record<string, number>; judgments?: Judgment[] } };
const labels: Record<string, string> = { accepted: "즉시 확정 가능", needs_verification: "확인 필요", rejected: "탈락", duplicate: "중복", candidate_pending: "접근 실패·재조사", ambiguous: "판정 보류" };

export default function ResearchAuditsScreen() {
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);
  const { data, loading, error, reload } = useResource(
    () => apiRequest<{ count: number; has_next: boolean; results: Run[] }>("/recommendations/admin/research-audits/", { params: { page } }),
    { count: 0, has_next: false, results: [] as Run[] }, true, String(page),
  );
  return <Screen title="수집 판정 기록" subtitle="수집기의 판정 기록입니다. 관리자 승인과는 다릅니다." back>
    <Pressable style={ui.button} onPress={() => router.push("/admin/evidence" as never)}><Text style={ui.buttonText}>DB에 저장된 근거 검토하기</Text></Pressable>
    <LoadState loading={loading} error={error} retry={reload} empty={!data.results.length} emptyText="아직 저장된 수집 기록이 없습니다." />
    {data.results.map(run => <View key={run.id} style={[ui.card, styles.run]}>
      <View style={ui.row}><View style={styles.runIcon}><Text style={styles.runIconText}>↻</Text></View><View style={ui.grow}><Text style={styles.runTitle}>{run.run_key}</Text><Text style={ui.muted}>수집기 실행 기록</Text></View></View>
      <View style={styles.stats}><View style={styles.stat}><Text style={styles.statValue}>{run.payload.rows ?? 0}</Text><Text style={styles.statLabel}>검사</Text></View><View style={styles.stat}><Text style={styles.statValue}>{run.payload.accepted ?? 0}</Text><Text style={styles.statLabel}>확정 가능</Text></View><View style={styles.stat}><Text style={styles.statValue}>{run.payload.needs_verification ?? 0}</Text><Text style={styles.statLabel}>확인 필요</Text></View></View>
      <Text style={ui.muted}>검사 {run.payload.rows ?? 0} · 즉시 확정 가능 {run.payload.accepted ?? 0} · 확인 필요 {run.payload.needs_verification ?? 0}</Text>
      <Text style={ui.muted}>탈락 {run.payload.rejected ?? 0} · 중복 {run.payload.duplicate ?? 0} · 저장 근거 {run.payload.saved ?? 0}</Text>
      {Object.entries(run.payload.reasons || {}).map(([reason, count]) => <Text key={reason} style={ui.muted}>{reason}: {count}건</Text>)}
      {run.payload.judgments?.length ? <>
        <Pressable style={ui.button} onPress={() => setExpanded(expanded === run.id ? null : run.id)}><Text style={ui.buttonText}>항목별 판정 {expanded === run.id ? "접기" : "보기"}</Text></Pressable>
        {expanded === run.id && run.payload.judgments.map((item, index) => <Text key={index} style={ui.muted}>{item.place_name} / {item.tag} · {labels[item.status] || item.status} · {item.reason}</Text>)}
      </> : <Text style={ui.muted}>과거 기록에는 항목별 판정이 저장되지 않아 합계만 제공됩니다.</Text>}
    </View>)}
    <View style={ui.row}>
      <Pressable disabled={loading || page === 1} onPress={() => setPage(page - 1)}><Text>이전</Text></Pressable>
      <Text>{page}페이지 · 총 {data.count}회</Text>
      <Pressable disabled={loading || !data.has_next} onPress={() => setPage(page + 1)}><Text>다음</Text></Pressable>
    </View>
  </Screen>;
}

const styles = StyleSheet.create({
  run: { gap: 11 },
  runIcon: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 13, backgroundColor: Palette.accentSoft },
  runIconText: { color: Palette.accent, fontSize: 20, fontWeight: "900" },
  runTitle: { color: Palette.ink, fontSize: 15, fontWeight: "900" },
  stats: { flexDirection: "row", gap: 6 },
  stat: { flex: 1, padding: 9, alignItems: "center", borderRadius: Radius.small, backgroundColor: Palette.surfaceMuted },
  statValue: { color: Palette.ink, fontSize: 16, fontWeight: "900" },
  statLabel: { marginTop: 2, color: Palette.muted, fontSize: 8 },
});
