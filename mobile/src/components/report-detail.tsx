import { useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { useResource } from "@/hooks/use-resource";
import { useAction } from "@/hooks/use-action";
import { LoadState } from "./load-state";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "./screen";
import {
  PLACE_CATEGORIES,
  normalizePlaceCategory,
  placeCategoryLabel,
} from "@/constants/place-categories";
import { PlaceMap } from "./place-map";
import type { Place } from "@/types/place";

type ReportData = {
  id?: number;
  place_name?: string;
  suggested_name?: string;
  suggested_category?: string;
  suggested_address?: string;
  description?: string;
  status?: string;
  status_label?: string;
  report_type_label?: string;
  report_type?: string;
  suggested_lat?: number;
  suggested_lng?: number;
  suggested_tags?: string[];
  admin_note?: string;
  created_at?: string;
  images?: { id: number; image_url: string }[];
};

export function ReportDetail({
  id,
  admin = false,
  receipt = false,
}: {
  id: string;
  admin?: boolean;
  receipt?: boolean;
}) {
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [reviewCategory, setReviewCategory] = useState("");
  const action = useAction();
  const { data, loading, error, reload } = useResource<ReportData>(
    () =>
      (admin
        ? recommendationApi.adminPlaceReport(id)
        : recommendationApi.myPlaceReport(id)) as Promise<ReportData>,
    {},
    true,
    id,
  );
  const effectiveCategory =
    reviewCategory || normalizePlaceCategory(data.suggested_category);
  const pendingAdmin = admin && Boolean(data.id) && !["approved", "rejected"].includes(data.status || "");
  const reportPlace: Place | null =
    Number.isFinite(Number(data.suggested_lat)) && Number.isFinite(Number(data.suggested_lng))
      ? {
          id: `report:${data.id || id}`,
          name: data.suggested_name || data.place_name || "제보 위치",
          category: data.suggested_category || "",
          address: data.suggested_address,
          lat: Number(data.suggested_lat),
          lng: Number(data.suggested_lng),
        }
      : null;
  const review = (approve: boolean) =>
    action.run(async () => {
      if (approve) {
        if (data.report_type === "new_place" && !effectiveCategory)
          throw new Error("새 장소의 카테고리를 선택해주세요.");
        await recommendationApi.approvePlaceReport(id, {
          admin_note: note,
          suggested_category: effectiveCategory || undefined,
        });
      }
      else await recommendationApi.rejectPlaceReport(id, { admin_note: note });
      setMessage(approve ? "승인했습니다." : "반려했습니다.");
      await reload();
    });
  return (
    <Screen
      title={receipt ? `제보 접수 #${id}` : admin ? `장소 제보 #${id}` : "제보 상세"}
      subtitle={admin ? "제출 내용과 위치를 확인한 뒤 처리해 주세요." : "접수 내용과 검토 진행 상태를 확인하세요."}
      back
      footer={pendingAdmin ? (
        <View style={styles.footerActions}>
          <Pressable disabled={action.busy} onPress={() => review(false)} style={[styles.rejectButton, action.busy && styles.disabled]}>
            <Text style={styles.rejectText}>반려</Text>
          </Pressable>
          <Pressable disabled={action.busy} onPress={() => review(true)} style={[ui.button, styles.footerButton, action.busy && styles.disabled]}>
            <Text style={ui.buttonText}>{action.busy ? "처리 중…" : "승인"}</Text>
          </Pressable>
        </View>
      ) : undefined}
    >
      {receipt ? (
        <View style={styles.receiptBanner}>
          <Text style={styles.receiptIcon}>✓</Text>
          <View style={ui.grow}>
            <Text style={styles.receiptTitle}>안전하게 접수되었습니다</Text>
            <Text style={ui.muted}>검토 결과는 제보 내역과 알림에서 확인할 수 있어요.</Text>
          </View>
        </View>
      ) : null}
      <LoadState loading={loading} error={error} retry={reload} />
      {data.id ? (
        <>
          <View style={ui.card}>
            <Text style={ui.sectionTitle}>
              {data.suggested_name || data.place_name}
            </Text>
            <Text style={ui.muted}>
              #{data.id} · {data.status_label || data.status} ·{" "}
              {data.report_type_label}
            </Text>
            <Text style={ui.muted}>
              {data.created_at
                ? new Date(data.created_at).toLocaleString()
                : ""}
            </Text>
            <Text>{data.suggested_address || "주소 미입력"}</Text>
            <Text style={ui.muted}>
              카테고리: {placeCategoryLabel(data.suggested_category)}
            </Text>
            <Text>{data.description}</Text>
            <Text style={ui.muted}>{data.suggested_tags?.join(" · ")}</Text>
          </View>
          {reportPlace ? (
            <View style={styles.mapCard}>
              <Text style={styles.sectionTitle}>제보 위치</Text>
              <PlaceMap place={reportPlace} displayMode="selected" focusSelected fitBoundsKey={`report-detail:${id}`} />
            </View>
          ) : (
            <Text style={ui.muted}>지도에 표시할 위치가 없습니다.</Text>
          )}
          {data.admin_note ? (
            <Text style={ui.success}>검토 메모: {data.admin_note}</Text>
          ) : null}
          {data.images?.length ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {data.images.map((image) => (
                <Image
                  key={image.id}
                  source={{ uri: image.image_url }}
                  style={{ width: 180, height: 140, marginRight: 8 }}
                  resizeMode="cover"
                />
              ))}
            </ScrollView>
          ) : (
            <Text style={ui.muted}>첨부 사진 없음</Text>
          )}
          {pendingAdmin ? (
            <>
              <Text style={ui.sectionTitle}>관리자 검토</Text>
              <Text style={ui.muted}>
                제보 내용과 사진을 확인한 뒤 승인하거나 반려해 주세요.
              </Text>
              {data.report_type === "new_place" || data.report_type === "edit_place" ? (
                <>
                  <Text style={ui.label}>
                    장소 카테고리{data.report_type === "new_place" ? " (승인 필수)" : ""}
                  </Text>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 7 }}>
                    {PLACE_CATEGORIES.map((item) => (
                      <Pressable
                        key={item.value}
                        onPress={() => setReviewCategory(item.value)}
                        accessibilityRole="radio"
                        accessibilityState={{ selected: effectiveCategory === item.value }}
                        style={[
                          ui.buttonSecondary,
                          { minHeight: 38 },
                          effectiveCategory === item.value
                            ? { borderColor: "#0F766E", backgroundColor: "#E6F4F1" }
                            : null,
                        ]}
                      >
                        <Text style={ui.buttonSecondaryText}>{item.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <Text style={ui.muted}>승인 적용: {placeCategoryLabel(effectiveCategory)}</Text>
                </>
              ) : null}
              <TextInput
                value={note}
                onChangeText={setNote}
                placeholder="사진·주소·제보 내용을 확인한 검토 메모"
                placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                multiline
                style={ui.textarea}
              />
            </>
          ) : null}
        </>
      ) : null}
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      {message ? <Text style={ui.success}>{message}</Text> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  receiptBanner: { padding: 16, flexDirection: "row", alignItems: "center", gap: 12, borderRadius: 18, backgroundColor: "#EAF8F1" },
  receiptIcon: { width: 38, height: 38, paddingTop: 7, borderRadius: 19, overflow: "hidden", backgroundColor: "#16875B", color: "#FFFFFF", fontSize: 18, fontWeight: "900", textAlign: "center" },
  receiptTitle: { color: "#116B49", fontSize: 15, fontWeight: "900" },
  mapCard: { gap: 10 },
  sectionTitle: { color: "#17201D", fontSize: 16, fontWeight: "900" },
  footerActions: { flexDirection: "row", gap: 8 },
  footerButton: { flex: 1 },
  rejectButton: { minHeight: 48, flex: 1, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#F0BABA", borderRadius: 12, backgroundColor: "#FFF0F0" },
  rejectText: { color: "#D94B4B", fontSize: 14, fontWeight: "900" },
  disabled: { opacity: 0.55 },
});
