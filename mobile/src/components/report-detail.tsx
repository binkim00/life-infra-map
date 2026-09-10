import { useState } from "react";
import { Image, Pressable, ScrollView, Text, TextInput, View } from "react-native";
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
    <Screen title={receipt ? "제보 접수 완료" : "제보 상세"} back>
      {receipt ? (
        <Text style={ui.success}>
          접수번호 #{id} · 서버에 접수되었습니다. 검토 결과는 제보 내역에서
          확인할 수 있습니다.
        </Text>
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
            <Text style={ui.muted}>
              위도 {data.suggested_lat ?? "미입력"} · 경도{" "}
              {data.suggested_lng ?? "미입력"}
            </Text>
            <Text>{data.description}</Text>
            <Text style={ui.muted}>{data.suggested_tags?.join(" · ")}</Text>
          </View>
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
          {admin && !["approved", "rejected"].includes(data.status || "") ? (
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
              <View style={ui.row}>
                <Pressable
                  disabled={action.busy}
                  onPress={() => review(true)}
                  style={ui.button}
                >
                  <Text style={ui.buttonText}>승인</Text>
                </Pressable>
                <Pressable
                  disabled={action.busy}
                  onPress={() => review(false)}
                  style={ui.buttonSecondary}
                >
                  <Text style={ui.buttonSecondaryText}>반려</Text>
                </Pressable>
              </View>
            </>
          ) : null}
        </>
      ) : null}
      {action.error ? <Text style={ui.error}>{action.error}</Text> : null}
      {message ? <Text style={ui.success}>{message}</Text> : null}
    </Screen>
  );
}
