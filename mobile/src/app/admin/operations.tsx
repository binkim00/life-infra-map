import { router } from "expo-router";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { Screen, ui } from "@/components/screen";
import { LoadState } from "@/components/load-state";
import { useResource } from "@/hooks/use-resource";

type Dashboard = {
  generated_at?: string;
  period?: {
    new_evidence?: number;
    evidence_places?: number;
    new_place_tags?: number;
    processed_places?: number;
  };
  cumulative?: { places?: number; evidence_places?: number };
  queue?: {
    queued?: number;
    processing?: number;
    retry?: number;
    failed?: number;
  };
  growth?: { date: string; new_evidence: number; new_place_tags: number }[];
  runtime?: { worker_last_success_at?: string };
};
export default function AdminOperationsScreen() {
  const [days, setDays] = useState(7);
  const { data, loading, error, reload } = useResource<Dashboard>(
    () => recommendationApi.adminOperations({ days }) as Promise<Dashboard>,
    {},
    true,
    String(days),
  );
  const metrics = [
    ["수집 완료 장소", data.period?.processed_places],
    ["신규 근거", data.period?.new_evidence],
    ["근거가 추가된 장소", data.period?.evidence_places],
    ["신규 통합 태그", data.period?.new_place_tags],
  ] as const;
  return (
    <Screen
      title="운영 현황"
      subtitle="수집 진행 · 근거 증가 · 검토할 작업"
      back
      action={
        <Pressable
          onPress={reload}
          disabled={loading}
          style={ui.buttonSecondary}
        >
          <Text>새로고침</Text>
        </Pressable>
      }
    >
      <View style={ui.row}>
        {[1, 7, 30].map((value) => (
          <Pressable
            key={value}
            onPress={() => setDays(value)}
            style={days === value ? ui.button : ui.buttonSecondary}
          >
            <Text
              style={days === value ? ui.buttonText : ui.buttonSecondaryText}
            >
              {value}일
            </Text>
          </Pressable>
        ))}
      </View>
      <LoadState
        loading={loading}
        error={error}
        empty={!data.generated_at}
        retry={reload}
      />
      {data.generated_at ? (
        <>
          <Text style={ui.muted}>
            집계 시각 {new Date(data.generated_at).toLocaleString()} · 수집 후 갱신되는 저장 집계입니다. 현재 실시간 수치와 다를 수 있습니다.
          </Text>
          <View style={[ui.row, { flexWrap: "wrap" }]}>
            {metrics.map(([label, value]) => (
              <View key={label} style={[ui.card, { minWidth: 140, flex: 1 }]}>
                <Text style={ui.sectionTitle}>
                  {value === undefined ? "집계 없음" : value.toLocaleString()}
                </Text>
                <Text style={ui.muted}>{label}</Text>
              </View>
            ))}
          </View>
          <View style={ui.card}>
            <Text style={ui.sectionTitle}>수집 작업</Text>
            <Text>
              대기 {data.queue?.queued ?? "—"} · 처리 중{" "}
              {data.queue?.processing ?? "—"}
            </Text>
            <Text>
              재시도 {data.queue?.retry ?? "—"} · 실패{" "}
              {data.queue?.failed ?? "—"}
            </Text>
            <Text style={ui.muted}>
              최근 완료{" "}
              {data.runtime?.worker_last_success_at
                ? new Date(data.runtime.worker_last_success_at).toLocaleString()
                : "기록 없음"}
            </Text>
          </View>
          <Pressable
            onPress={() => router.push("/admin/evidence" as never)}
            style={ui.button}
          >
            <Text style={ui.buttonText}>수집 근거 원문·확인 필요 검토</Text>
          </Pressable>
          <Pressable
            onPress={() => router.push("/admin/place-reports")}
            style={ui.buttonSecondary}
          >
            <Text style={ui.buttonSecondaryText}>사용자 장소 제보 검토</Text>
          </Pressable>
          <View style={ui.card}>
            <Text style={ui.sectionTitle}>일별 증가</Text>
            <Text style={ui.muted}>날짜 · 신규 근거 · 신규 통합 태그</Text>
            {data.growth?.length ? (
              data.growth.map((row) => (
                <Text key={row.date}>
                  {row.date} · {row.new_evidence}개 · {row.new_place_tags}개
                </Text>
              ))
            ) : (
              <Text style={ui.muted}>집계된 일별 내역이 없습니다.</Text>
            )}
          </View>
          <Text style={ui.muted}>
            신규 근거 수가 늘어도 검색 조건이 검증되었다는 뜻은 아닙니다. 근거
            검토와 태그 집계 결과를 함께 확인하세요. 검색 속도와 배포 품질
            지표는 이 화면에 아직 연결되지 않았습니다.
          </Text>
        </>
      ) : null}
    </Screen>
  );
}
