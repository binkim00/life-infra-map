import * as ImagePicker from "expo-image-picker";
import { searchLocation } from "@/utils/location";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { recommendationApi } from "@/api/recommendations";
import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/auth-context";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { PlaceMap } from "@/components/place-map";
import type { Place } from "@/types/place";
import {
  PLACE_CATEGORIES,
  placeCategoryLabel,
} from "@/constants/place-categories";
import {
  clearPlaceReportDraft,
  createReportRequestId,
  loadPlaceReportDraft,
  persistDraftImages,
  PlaceReportDraft,
  removeDraftImages,
  reportDraftKey,
  ReportDraftImage,
  savePlaceReportDraft,
} from "@/utils/place-report-draft";

const TYPES = [
  { value: "new_place", label: "새로운 장소" },
  { value: "tag_suggestion", label: "태그 추가" },
  { value: "wrong_info", label: "잘못된 정보" },
  { value: "edit_place", label: "장소 정보 수정" },
];
const TAGS = [
  "조용함",
  "노트북 작업 가능",
  "콘센트 있음",
  "와이파이 있음",
  "혼자 이용 좋음",
  "잠깐 쉬기 좋음",
  "산책하기 좋음",
  "주차 가능",
];

type ReportParams = {
    placeId?: string;
    name?: string;
    address?: string;
    lat?: string;
    lng?: string;
};

export default function PlaceReportScreen() {
  const params = useLocalSearchParams<ReportParams>();
  const { user } = useAuth();
  return <PlaceReportForm key={`${user?.id || "anonymous"}:${JSON.stringify(params)}`} params={params} />;
}

function PlaceReportForm({ params }: { params: ReportParams }) {
  const { ready, isLoggedIn, requireLogin, user } = useAuth();
  const [type, setType] = useState(
    params.placeId ? "tag_suggestion" : "new_place",
  );
  const [name, setName] = useState(params.name || "");
  const [category, setCategory] = useState("");
  const [address, setAddress] = useState(params.address || "");
  const [lat, setLat] = useState(params.lat || "");
  const [lng, setLng] = useState(params.lng || "");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [images, setImages] = useState<ReportDraftImage[]>([]);
  const [requestId, setRequestId] = useState(createReportRequestId);
  const [deviceLocation, setDeviceLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [draftReady, setDraftReady] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  const draftKey = useMemo(() => reportDraftKey(params.placeId,
    params.name ? JSON.stringify([params.name, params.address || "", params.lat || "", params.lng || ""]) : undefined),
    [params.placeId, params.name, params.address, params.lat, params.lng]);
  const ownerKey = user?.id ? `user:${user.id}` : user?.username ? `username:${user.username}` : "anonymous";
  const pickedPlace = useMemo<Place | null>(() => {
    if (!lat.trim() || !lng.trim()) return null;
    const parsedLat = Number(lat);
    const parsedLng = Number(lng);
    if (!Number.isFinite(parsedLat) || !Number.isFinite(parsedLng)) return null;
    return {
      id: "report-pin",
      name: name.trim() || "제보 위치",
      category: "제보 위치",
      lat: parsedLat,
      lng: parsedLng,
    };
  }, [lat, lng, name]);
  const chooseMapCoordinate = ({ lat: nextLat, lng: nextLng }: { lat: number; lng: number }) => {
    setLat(nextLat.toFixed(6));
    setLng(nextLng.toFixed(6));
    setMessage("지도에서 제보 위치를 지정했습니다.");
  };

  useEffect(() => {
    if (!ready) return;
    let active = true;
    void loadPlaceReportDraft(draftKey).then((draft) => {
      if (!active) return;
      if (draft && (draft.ownerKey === ownerKey || draft.ownerKey === "anonymous")) {
        setType(draft.type || (params.placeId ? "tag_suggestion" : "new_place"));
        setName(draft.name || "");
        setCategory(draft.category || "");
        setAddress(draft.address || "");
        setLat(draft.lat || "");
        setLng(draft.lng || "");
        setDescription(draft.description || "");
        setTags(Array.isArray(draft.tags) ? draft.tags : []);
        setImages(Array.isArray(draft.images) ? draft.images : []);
        setRequestId(draft.requestId);
        setMessage("저장된 제보 초안을 불러왔습니다.");
      }
      setDraftReady(true);
    }).catch(() => {
      if (active) setDraftReady(true);
    });
    return () => { active = false; };
  }, [draftKey, ownerKey, params.placeId, params.name, params.address, params.lat, params.lng, ready]);

  useEffect(() => {
    if (!draftReady) return;
    const hasContent = Boolean(name || address || lat || lng || description || tags.length || images.length);
    if (!hasContent) return;
    const draft: PlaceReportDraft = {
      version: 2,
      ownerKey,
      requestId,
      type,
      category,
      name,
      address,
      lat,
      lng,
      description,
      tags,
      images,
      updatedAt: new Date().toISOString(),
    };
    const timer = setTimeout(() => {
      void savePlaceReportDraft(draftKey, draft);
    }, 300);
    return () => clearTimeout(timer);
  }, [address, category, description, draftKey, draftReady, images, lat, lng, name, ownerKey, requestId, tags, type]);
  const locate = async () => {
    try {
      if (locating) return;
      setLocating(true);
      const coordinates = await searchLocation();
      if (!coordinates) return setMessage("위치 권한이 필요합니다.");
      setLat(coordinates.latitude.toFixed(6));
      setLng(coordinates.longitude.toFixed(6));
      setDeviceLocation({ lat: coordinates.latitude, lng: coordinates.longitude });
      setMessage("현재 위치를 입력했습니다.");
    } catch {
      setMessage("현재 위치를 확인하지 못했습니다.");
    } finally {
      setLocating(false);
    }
  };
  const pick = async () => {
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setMessage("사진을 첨부하려면 사진 접근 권한을 허용해 주세요.");
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsMultipleSelection: true,
        selectionLimit: 5,
        quality: 0.8,
      });
      if (!result.canceled) {
        const durable = await persistDraftImages(result.assets, requestId);
        await removeDraftImages(images);
        setImages(durable);
        setMessage("사진을 포함해 초안을 이 기기에 저장했습니다.");
      }
    } catch {
      setMessage("사진을 불러오지 못했습니다.");
    }
  };
  const submit = async () => {
    if (!requireLogin()) return;
    if (!name.trim() || !lat || !lng || !description.trim())
      return setMessage("장소명, 위치, 제보 내용을 입력해주세요.");
    if (type === "new_place" && !category)
      return setMessage("새 장소의 카테고리를 선택해주세요.");
    const body = new FormData();
    body.append("client_request_id", requestId);
    body.append("report_type", type);
    if (params.placeId) body.append("place", params.placeId);
    body.append("suggested_name", name);
    if (category) body.append("suggested_category", category);
    body.append("suggested_address", address);
    body.append("suggested_lat", lat);
    body.append("suggested_lng", lng);
    body.append("description", description);
    body.append("suggested_tags", JSON.stringify(tags));
    images.forEach((image) =>
      body.append("images", {
        uri: image.uri,
        name: image.fileName || "report.jpg",
        type: image.mimeType || "image/jpeg",
      } as unknown as Blob),
    );
    try {
      setLoading(true);
      const receipt = await recommendationApi.createPlaceReport(body);
      await clearPlaceReportDraft(draftKey, images);
      setRequestId(createReportRequestId());
      router.replace({ pathname: "/mypage/report-detail" as never, params: { id: String(receipt.report.id), receipt: "1" } });
    } catch (error) {
      const details = error instanceof ApiError && error.status === 400 && error.data && typeof error.data === "object"
        ? Object.values(error.data).flat().filter(value => typeof value === "string").join("\n") : "";
      setMessage(details || (error instanceof Error ? error.message : "제보 접수에 실패했습니다."));
    } finally {
      setLoading(false);
    }
  };
  if (!ready) {
    return (
      <Screen title="장소 정보 제보" back>
        <ActivityIndicator color="#0F766E" />
      </Screen>
    );
  }
  return (
    <Screen
      title="장소 제보"
      subtitle="빠진 장소와 달라진 정보를 알려주세요. 검토 후 검색에 반영됩니다."
      back
      footer={
        <Pressable
          accessibilityRole="button"
          disabled={loading}
          onPress={submit}
          style={[ui.button, loading && styles.disabled]}
        >
          <Text style={ui.buttonText}>{loading ? "안전하게 접수하는 중…" : "제보 접수"}</Text>
        </Pressable>
      }
    >
      {!isLoggedIn ? (
        <Text style={ui.muted}>
          새 장소를 등록하거나 잘못된 정보를 알려주세요. 제보를 접수하려면
          로그인이 필요합니다.
        </Text>
      ) : null}
      <View style={styles.draftNotice}>
        <Text style={styles.draftTitle}>작성 중인 내용은 자동 저장돼요</Text>
        <Text style={ui.muted}>앱을 닫아도 접수 전까지 이 기기에서 다시 이어 쓸 수 있습니다.</Text>
      </View>
      <View style={styles.options}>
        {TYPES.map((item) => (
          <Pressable
            key={item.value}
            onPress={() => setType(item.value)}
            style={[styles.option, type === item.value && styles.optionActive]}
          >
            <Text
              style={[
                styles.optionText,
                type === item.value && styles.optionTextActive,
              ]}
            >
              {item.label}
            </Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.sectionTitle}>기본 정보</Text>
      <TextInput
        value={name}
        onChangeText={setName}
        placeholder="장소명"
        placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
        style={ui.input}
      />
      {type === "new_place" || type === "edit_place" ? (
        <>
          <Text style={ui.label}>
            장소 카테고리{type === "new_place" ? " (필수)" : " (변경할 때만 선택)"}
          </Text>
          <View style={styles.tags}>
            {PLACE_CATEGORIES.map((item) => (
              <Pressable
                key={item.value}
                onPress={() => setCategory(item.value)}
                accessibilityRole="radio"
                accessibilityState={{ selected: category === item.value }}
                style={[styles.tag, category === item.value && styles.tagActive]}
              >
                <Text style={styles.tagText}>{item.label}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={ui.muted}>선택: {placeCategoryLabel(category)}</Text>
        </>
      ) : null}
      <TextInput
        value={address}
        onChangeText={setAddress}
        placeholder="주소"
        placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
        style={ui.input}
      />
      <Text style={styles.sectionTitle}>지도에서 위치 선택</Text>
      <Text style={ui.muted}>지도를 움직인 뒤 원하는 지점을 누르거나 현재 위치를 사용하세요.</Text>
      <View style={ui.row}>
        <TextInput
          value={lat}
          onChangeText={setLat}
          keyboardType="numeric"
          placeholder="위도"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={[ui.input, ui.grow]}
        />
        <TextInput
          value={lng}
          onChangeText={setLng}
          keyboardType="numeric"
          placeholder="경도"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          style={[ui.input, ui.grow]}
        />
      </View>
      <Pressable disabled={locating} onPress={locate} style={[ui.buttonSecondary, locating && styles.disabled]}>
        <Text style={ui.buttonSecondaryText}>{locating ? "위치 확인 중…" : "현재 위치 사용"}</Text>
      </Pressable>
      <PlaceMap
        place={pickedPlace}
        displayMode="selected"
        onMapPress={chooseMapCoordinate}
        onRequestCurrentLocation={locate}
        currentLocation={deviceLocation}
        fitBoundsKey={pickedPlace ? `report-pin:${pickedPlace.lat}:${pickedPlace.lng}` : "report-pin-empty"}
      />
      <Text style={styles.sectionTitle}>장소 특징</Text>
      <View style={styles.tags}>
        {TAGS.map((tag) => (
          <Pressable
            key={tag}
            onPress={() =>
              setTags((current) =>
                current.includes(tag)
                  ? current.filter((v) => v !== tag)
                  : [...current, tag],
              )
            }
            style={[styles.tag, tags.includes(tag) && styles.tagActive]}
          >
            <Text style={styles.tagText}>{tag}</Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.sectionTitle}>제보 내용</Text>
      <TextInput
        value={description}
        onChangeText={setDescription}
        placeholder="제보 내용을 입력하세요"
        placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
        multiline
        style={ui.textarea}
      />
      <Pressable accessibilityRole="button" onPress={pick} style={ui.buttonSecondary}>
        <Text style={ui.buttonSecondaryText}>
          사진 선택 ({images.length}/5)
        </Text>
      </Pressable>
      <View style={styles.images}>
        {images.map((image) => (
          <View key={image.uri} style={styles.imageWrap}>
            <Image source={{ uri: image.uri }} style={styles.image} />
            <Pressable
              accessibilityLabel="첨부 사진 삭제"
              onPress={() => {
                void removeDraftImages([image]);
                setImages((current) => current.filter((item) => item.uri !== image.uri));
              }}
              style={styles.removeImage}
            >
              <Text style={styles.removeImageText}>×</Text>
            </Pressable>
          </View>
        ))}
      </View>
      {message ? (
        <Text style={/(필요|못|실패|입력|선택해)/.test(message) ? ui.error : ui.success}>{message}</Text>
      ) : null}
    </Screen>
  );
}
const styles = StyleSheet.create({
  options: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  option: {
    paddingHorizontal: 11,
    paddingVertical: 9,
    borderRadius: 999,
    backgroundColor: "#FFFFFF",
  },
  optionActive: { backgroundColor: "#222222" },
  optionText: { color: "#686159", fontSize: 10, fontWeight: "800" },
  optionTextActive: { color: "#FFFFFF" },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  tag: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: "#DCE3DF",
    borderRadius: 999,
  },
  tagActive: { borderColor: "#0F766E", backgroundColor: "#E6F4F1" },
  tagText: { color: "#38403C", fontSize: 10, fontWeight: "700" },
  images: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  image: { width: 72, height: 72, borderRadius: 9 },
  imageWrap: { position: "relative" },
  removeImage: { position: "absolute", top: -6, right: -6, width: 24, height: 24, alignItems: "center", justifyContent: "center", borderRadius: 12, backgroundColor: "#17201D" },
  removeImageText: { marginTop: -2, color: "#FFFFFF", fontSize: 18, fontWeight: "800" },
  sectionTitle: { marginTop: 4, color: "#17201D", fontSize: 16, fontWeight: "900" },
  draftNotice: { padding: 14, gap: 4, borderRadius: 14, backgroundColor: "#E9F5F2" },
  draftTitle: { color: "#0F857A", fontSize: 12, fontWeight: "900" },
  disabled: { opacity: 0.55 },
});
