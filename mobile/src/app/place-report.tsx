import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
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
import { useAuth } from "@/auth/auth-context";
import { Screen, ui } from "@/components/screen";

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
  const { ready, isLoggedIn } = useAuth();
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
  const [images, setImages] = useState<ImagePicker.ImagePickerAsset[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const locate = async () => {
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) return setMessage("위치 권한이 필요합니다.");
      const position = await Location.getCurrentPositionAsync({});
      setLat(String(position.coords.latitude));
      setLng(String(position.coords.longitude));
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
      if (!result.canceled) setImages(result.assets);
    } catch {
      setMessage("사진을 불러오지 못했습니다.");
    }
  };
  const submit = async () => {
    if (!name.trim() || !lat || !lng || !description.trim())
      return setMessage("장소명, 위치, 제보 내용을 입력해주세요.");
    const body = new FormData();
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
      await recommendationApi.createPlaceReport(body);
      router.replace("/mypage/reports");
    } catch {
      setMessage("제보 접수에 실패했습니다.");
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
  if (ready && !isLoggedIn) {
    return <Redirect href="/login" />;
  }
  return (
    <Screen
      title="장소 정보 제보"
      subtitle="관리자 검토 후 검색 데이터에 반영됩니다."
      back
    >
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
        style={ui.input}
      />
      <TextInput
        value={address}
        onChangeText={setAddress}
        placeholder="주소"
        style={ui.input}
      />
      <View style={ui.row}>
        <TextInput
          value={lat}
          onChangeText={setLat}
          keyboardType="numeric"
          placeholder="위도"
          style={[ui.input, ui.grow]}
        />
        <TextInput
          value={lng}
          onChangeText={setLng}
          keyboardType="numeric"
          placeholder="경도"
          style={[ui.input, ui.grow]}
        />
      </View>
      <Pressable onPress={locate} style={ui.buttonSecondary}>
        <Text style={ui.buttonSecondaryText}>현재 위치 사용</Text>
      </Pressable>
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
