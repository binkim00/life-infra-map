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

export default function PlaceReportScreen() {
  const { ready, isLoggedIn, requireLogin, user } = useAuth();
  const params = useLocalSearchParams<{
    placeId?: string;
    name?: string;
    address?: string;
    lat?: string;
    lng?: string;
  }>();
  const [type, setType] = useState(
    params.placeId ? "tag_suggestion" : "new_place",
  );
  const [name, setName] = useState(params.name || "");
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
  const draftKey = useMemo(() => reportDraftKey(params.placeId), [params.placeId]);
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
  }, [draftKey, ownerKey, params.placeId, ready]);

  useEffect(() => {
    if (!draftReady) return;
    const hasContent = Boolean(name || address || lat || lng || description || tags.length || images.length);
    if (!hasContent) return;
    const draft: PlaceReportDraft = {
      version: 2,
      ownerKey,
      requestId,
      type,
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
  }, [address, description, draftKey, draftReady, images, lat, lng, name, ownerKey, requestId, tags, type]);
  const locate = async () => {
    try {
      const coordinates = await searchLocation();
      if (!coordinates) return setMessage("위치 권한이 필요합니다.");
      setLat(coordinates.latitude.toFixed(6));
      setLng(coordinates.longitude.toFixed(6));
      setDeviceLocation({ lat: coordinates.latitude, lng: coordinates.longitude });
      setMessage("현재 위치를 입력했습니다.");
    } catch {
      setMessage("현재 위치를 확인하지 못했습니다.");
    }
  };
  const pick = async () => {
    try {
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
    const body = new FormData();
    body.append("client_request_id", requestId);
    body.append("report_type", type);
    if (params.placeId) body.append("place", params.placeId);
    body.append("suggested_name", name);
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
      title="장소 정보 제보"
      subtitle="관리자 검토 후 검색 데이터에 반영됩니다."
      back
    >
      {!isLoggedIn ? (
        <Text style={ui.muted}>
          새 장소를 등록하거나 잘못된 정보를 알려주세요. 제보를 접수하려면
          로그인이 필요합니다.
        </Text>
      ) : null}
      <Text style={ui.muted}>작성 내용과 선택한 사진은 접수될 때까지 이 기기에 자동 저장됩니다.</Text>
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
      <TextInput
        value={name}
        onChangeText={setName}
        placeholder="장소명"
        placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
        style={ui.input}
      />
      <TextInput
        value={address}
        onChangeText={setAddress}
        placeholder="주소"
        placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
        style={ui.input}
      />
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
      <Pressable onPress={locate} style={ui.buttonSecondary}>
        <Text style={ui.buttonSecondaryText}>현재 위치 사용</Text>
      </Pressable>
      <Text style={ui.muted}>지도를 이동한 뒤 원하는 지점을 누르면 핀이 표시됩니다.</Text>
      <PlaceMap
        place={pickedPlace}
        displayMode="selected"
        onMapPress={chooseMapCoordinate}
        onRequestCurrentLocation={locate}
        currentLocation={deviceLocation}
        fitBoundsKey={pickedPlace ? `report-pin:${pickedPlace.lat}:${pickedPlace.lng}` : "report-pin-empty"}
      />
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
      <TextInput
        value={description}
        onChangeText={setDescription}
        placeholder="제보 내용을 입력하세요"
        placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
        multiline
        style={ui.textarea}
      />
      <Pressable onPress={pick} style={ui.buttonSecondary}>
        <Text style={ui.buttonSecondaryText}>
          사진 선택 ({images.length}/5)
        </Text>
      </Pressable>
      <View style={styles.images}>
        {images.map((image) => (
          <Image
            key={image.uri}
            source={{ uri: image.uri }}
            style={styles.image}
          />
        ))}
      </View>
      {message ? <Text style={ui.error}>{message}</Text> : null}
      <Pressable disabled={loading} onPress={submit} style={ui.button}>
        <Text style={ui.buttonText}>
          {loading ? "접수 중..." : "제보 접수"}
        </Text>
      </Pressable>
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
});
