import { recommendationApi } from "@/api/recommendations";
import { router, useLocalSearchParams } from "expo-router";
import { PlaceDetailSheet } from "@/components/place-detail-sheet";
import type { Place } from "@/types/place";
import { useAuth } from "@/auth/auth-context";
import { BottomNav } from "@/components/bottom-nav";
import { LoadState } from "@/components/load-state";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { useResource } from "@/hooks/use-resource";
import { useMemo, useRef, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { AppIcon } from "@/components/app-icon";
import { PlacePhoto } from "@/components/place-photo";
import { Palette, Radius } from "@/constants/theme";

type SavedPlaceGroup = {
  id: number;
  name: string;
  memo?: string;
};

type SavedPlace = {
  id: number;
  place?: number | null;
  category?: string;
  lat?: number | null;
  lng?: number | null;
  detail_url?: string;
  kakao_place_url?: string;
  source?: string;
  name?: string;
  place_name?: string;
  address?: string;
  memo?: string;
  group_id?: number | null;
  group_name?: string;
};

export default function SavedPlacesScreen() {
  const { savedId } = useLocalSearchParams<{ savedId?: string }>();
  const openedId = useRef<string | undefined>(undefined);
  const { ready, isLoggedIn } = useAuth();
  const [groups, setGroups] = useState<SavedPlaceGroup[]>([]);
  const [places, setPlaces] = useState<SavedPlace[]>([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [showGroupMaker, setShowGroupMaker] = useState(false);
  const [showGroupSettings, setShowGroupSettings] = useState(false);
  const [groupNameDrafts, setGroupNameDrafts] = useState<Record<number, string>>({});
  const [groupMemoDrafts, setGroupMemoDrafts] = useState<Record<number, string>>({});
  const [placeMemoDrafts, setPlaceMemoDrafts] = useState<Record<number, string>>({});
  const [busyKey, setBusyKey] = useState("");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<Place | null>(null);
  const openPlace = (place: SavedPlace) => setSelected({
    id: place.place ?? `saved:${place.id}`, name: place.place_name || place.name || "저장 장소",
    category: place.category || "", address: place.address,
    lat: place.lat == null ? NaN : Number(place.lat), lng: place.lng == null ? NaN : Number(place.lng),
    place_url: place.detail_url, kakao_place_url: place.kakao_place_url,
    result_source: place.place ? "db" : place.source || "external",
  });

  const load = async () => {
    const [groupResponse, placeResponse] = await Promise.all([
      recommendationApi.savedPlaceGroups(),
      recommendationApi.savedPlaces({ page: 1, page_size: 100 }),
    ]);
    setGroups((groupResponse as { results?: SavedPlaceGroup[] }).results || []);
    setPlaces((placeResponse as { results?: SavedPlace[] }).results || []);
    const requested = (placeResponse as { results?: SavedPlace[] }).results?.find(p => String(p.id) === savedId);
    if (requested && openedId.current !== savedId) {
      openedId.current = savedId;
      openPlace(requested);
    }
  };
  const { loading, error, reload } = useResource(load, undefined, ready && isLoggedIn, savedId);

  const placesByGroup = useMemo(() => {
    const grouped = new Map<number | null, SavedPlace[]>();
    grouped.set(null, []);
    groups.forEach((group) => grouped.set(group.id, []));
    places.forEach((place) => {
      const key = place.group_id && grouped.has(place.group_id) ? place.group_id : null;
      grouped.get(key)?.push(place);
    });
    return grouped;
  }, [groups, places]);

  const run = async (key: string, action: () => Promise<void>) => {
    if (busyKey) return;
    setBusyKey(key);
    setMessage("");
    try {
      await action();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "요청을 처리하지 못했습니다.");
    } finally {
      setBusyKey("");
    }
  };

  const createGroup = () => run("create", async () => {
    const name = newGroupName.trim();
    if (!name) {
      setMessage("그룹 이름을 입력해 주세요.");
      return;
    }
    const created = await recommendationApi.createSavedPlaceGroup({ name, memo: "" }) as SavedPlaceGroup;
    setGroups((current) => [created, ...current]);
    setNewGroupName("");
    setMessage(`‘${created.name}’ 그룹을 만들었습니다.`);
  });

  const saveGroup = (group: SavedPlaceGroup) => run(`group-${group.id}`, async () => {
    const name = (groupNameDrafts[group.id] ?? group.name).trim();
    if (!name) {
      setMessage("그룹 이름을 입력해 주세요.");
      return;
    }
    const updated = await recommendationApi.updateSavedPlaceGroup(group.id, {
      name,
      memo: groupMemoDrafts[group.id] ?? group.memo ?? "",
    }) as SavedPlaceGroup;
    setGroups((current) => current.map((item) => item.id === group.id ? updated : item));
    setPlaces((current) => current.map((place) =>
      place.group_id === group.id ? { ...place, group_name: updated.name } : place));
    setMessage("그룹 이름과 메모를 저장했습니다.");
  });

  const deleteGroup = (group: SavedPlaceGroup) => {
    Alert.alert("그룹 삭제", `‘${group.name}’ 그룹을 삭제할까요? 장소는 미분류에 남습니다.`, [
      { text: "취소", style: "cancel" },
      {
        text: "삭제",
        style: "destructive",
        onPress: () => run(`delete-${group.id}`, async () => {
          await recommendationApi.deleteSavedPlaceGroup(group.id);
          setGroups((current) => current.filter((item) => item.id !== group.id));
          setPlaces((current) => current.map((place) =>
            place.group_id === group.id ? { ...place, group_id: null, group_name: "" } : place));
          setMessage("그룹을 삭제했습니다. 장소는 미분류에 남겨 두었습니다.");
        }),
      },
    ]);
  };

  const movePlace = (place: SavedPlace, groupId: number | null) =>
    run(`move-${place.id}`, async () => {
      const updated = await recommendationApi.moveSavedPlaceToGroup(place.id, groupId) as SavedPlace;
      setPlaces((current) => current.map((item) => item.id === place.id ? updated : item));
      setMessage(groupId ? "장소를 그룹으로 옮겼습니다." : "장소를 미분류로 옮겼습니다.");
    });

  const savePlaceMemo = (place: SavedPlace) => run(`memo-${place.id}`, async () => {
    const updated = await recommendationApi.updateSavedPlace(place.id, {
      memo: placeMemoDrafts[place.id] ?? place.memo ?? "",
    }) as SavedPlace;
    setPlaces((current) => current.map((item) => item.id === place.id ? updated : item));
    setMessage("장소 메모를 저장했습니다.");
  });

  const deletePlace = (place: SavedPlace) => {
    Alert.alert("저장 장소 삭제", `‘${place.place_name || place.name || "이 장소"}’를 보관함에서 삭제할까요?`, [
      { text: "취소", style: "cancel" },
      {
        text: "삭제",
        style: "destructive",
        onPress: () => run(`place-delete-${place.id}`, async () => {
          await recommendationApi.deleteSavedPlace(place.id);
          setPlaces((current) => current.filter((item) => item.id !== place.id));
          setMessage("저장한 장소를 삭제했습니다.");
        }),
      },
    ]);
  };

  const renderPlace = (place: SavedPlace) => (
    <View key={place.id} style={[ui.card, styles.placeCard]}>
      <Pressable accessibilityRole="button" onPress={() => openPlace(place)} style={styles.placeTop}>
        <PlacePhoto category={place.category} fallback={place.id} width={82} height={82} style={styles.placePhoto} externalUrl={place.kakao_place_url || place.detail_url} source={place.source} />
        <View style={styles.placeCopy}>
          <Text style={styles.placeName}>{place.place_name || place.name || "이름 없는 장소"}</Text>
          {place.address ? <Text numberOfLines={2} style={ui.muted}>{place.address}</Text> : <Text style={ui.muted}>주소 정보 없음</Text>}
          <Text style={styles.detailLink}>장소 상세 보기  ›</Text>
        </View>
      </Pressable>
      <View style={styles.memoBox}>
        <Text style={styles.memoLabel}>메모</Text>
        <TextInput
          value={placeMemoDrafts[place.id] ?? place.memo ?? ""}
          onChangeText={(value) => setPlaceMemoDrafts((current) => ({ ...current, [place.id]: value }))}
          placeholder="이 장소에 대한 메모"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          multiline
          style={styles.memoInput}
        />
        <Pressable onPress={() => savePlaceMemo(place)} style={styles.memoSave}><Text style={styles.memoSaveText}>저장</Text></Pressable>
      </View>
      <View style={styles.placeFooter}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
          <Pressable onPress={() => movePlace(place, null)} style={[styles.chip, !place.group_id && styles.chipActive]}><Text style={[styles.chipText, !place.group_id && styles.chipTextActive]}>미분류</Text></Pressable>
          {groups.map((group) => <Pressable key={group.id} onPress={() => movePlace(place, group.id)} style={[styles.chip, place.group_id === group.id && styles.chipActive]}><Text style={[styles.chipText, place.group_id === group.id && styles.chipTextActive]}>{group.name}</Text></Pressable>)}
        </ScrollView>
        <Pressable onPress={() => deletePlace(place)}><Text style={styles.delete}>삭제</Text></Pressable>
      </View>
    </View>
  );

  const selectedGroup = groups.find((group) => group.id === selectedGroupId);
  const selectedPlaces = placesByGroup.get(selectedGroupId) || [];

  return (
    <View style={styles.root}>
      <Screen title="장소 보관함" subtitle="원하는 그룹으로 나누고 메모를 남겨 보세요.">
        <LoadState loading={loading} error={error} retry={reload} />
        {!loading && !error ? (
          <>
            <View style={styles.headingRow}>
              <View><Text style={ui.sectionTitle}>내 그룹</Text><Text style={ui.muted}>그룹을 눌러 저장한 장소를 모아보세요.</Text></View>
              <Pressable onPress={() => setShowGroupMaker((value) => !value)} style={styles.addGroup}><AppIcon ios="plus" android="add" size={17} color={Palette.accent} /><Text style={styles.addGroupText}>그룹 만들기</Text></Pressable>
            </View>
            {showGroupMaker ? <View style={[ui.card, styles.groupMaker]}>
              <Text style={ui.label}>새 그룹 이름</Text>
              <View style={styles.row}>
                <TextInput
                  value={newGroupName}
                  onChangeText={setNewGroupName}
                  placeholder="예: 부모님과 갈 곳"
                  placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                  maxLength={100}
                  style={[ui.input, styles.grow]}
                />
                <Pressable onPress={createGroup} style={ui.button}>
                  <Text style={ui.buttonText}>만들기</Text>
                </Pressable>
              </View>
            </View> : null}

            {message ? <Text style={styles.message}>{message}</Text> : null}

            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.groupRow}>
              <Pressable onPress={() => { setSelectedGroupId(null); setShowGroupSettings(false); }} style={[styles.groupTile, styles.groupTileMint, selectedGroupId === null && styles.groupTileSelected]}>
                <AppIcon ios="tray.full.fill" android="inbox" size={22} color={Palette.accentDark} /><Text style={styles.groupTileName}>미분류</Text><Text style={styles.groupCount}>{(placesByGroup.get(null) || []).length}곳</Text>
              </Pressable>
              {groups.map((group, index) => <Pressable key={group.id} onPress={() => { setSelectedGroupId(group.id); setShowGroupSettings(false); }} style={[styles.groupTile, index % 3 === 0 ? styles.groupTileCoral : index % 3 === 1 ? styles.groupTileLavender : styles.groupTileAmber, selectedGroupId === group.id && styles.groupTileSelected]}>
                <AppIcon ios={index % 2 ? "person.2.fill" : "heart.fill"} android={index % 2 ? "group" : "favorite"} size={22} color={Palette.ink} /><Text numberOfLines={1} style={styles.groupTileName}>{group.name}</Text><Text style={styles.groupCount}>{(placesByGroup.get(group.id) || []).length}곳</Text>
              </Pressable>)}
            </ScrollView>

            {selectedGroup ? <View style={styles.selectedHeader}><View><Text style={ui.sectionTitle}>{selectedGroup.name}</Text>{selectedGroup.memo ? <Text style={ui.muted}>{selectedGroup.memo}</Text> : null}</View><Pressable onPress={() => setShowGroupSettings((value) => !value)} style={styles.settingsButton}><AppIcon ios="ellipsis" android="more_horiz" size={20} color={Palette.muted} /></Pressable></View> : <Text style={ui.sectionTitle}>미분류</Text>}
            {selectedGroup && showGroupSettings ? <View style={[ui.card, styles.groupSettings]}>
                <Text style={ui.label}>그룹 이름과 설명</Text>
                <TextInput
                  value={groupNameDrafts[selectedGroup.id] ?? selectedGroup.name}
                  onChangeText={(value) => setGroupNameDrafts((current) => ({ ...current, [selectedGroup.id]: value }))}
                  placeholder="그룹 이름"
                  placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                  maxLength={100}
                  style={ui.input}
                />
                <TextInput
                  value={groupMemoDrafts[selectedGroup.id] ?? selectedGroup.memo ?? ""}
                  onChangeText={(value) => setGroupMemoDrafts((current) => ({ ...current, [selectedGroup.id]: value }))}
                  placeholder="이 그룹에 대한 메모"
                  placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                  multiline
                  style={[ui.input, styles.groupMemo]}
                />
                <View style={styles.actions}>
                  <Pressable onPress={() => saveGroup(selectedGroup)} style={ui.buttonSecondary}>
                    <Text style={ui.buttonSecondaryText}>이름·메모 저장</Text>
                  </Pressable>
                  <Pressable onPress={() => deleteGroup(selectedGroup)}>
                    <Text style={styles.delete}>그룹 삭제</Text>
                  </Pressable>
                </View>
              </View> : null}
            <View style={styles.section}>{selectedPlaces.length ? selectedPlaces.map(renderPlace) : <View style={styles.emptyGroup}><AppIcon ios="bookmark" android="bookmark" size={30} color="#9BA8A2" /><Text style={styles.emptyTitle}>이 그룹은 아직 비어 있어요</Text><Text style={ui.muted}>검색 결과에서 저장 버튼을 눌러 장소를 담아보세요.</Text></View>}</View>
          </>
        ) : null}
      </Screen>
      <PlaceDetailSheet place={selected} visible={Boolean(selected)} onClose={() => setSelected(null)}
        onSave={() => setMessage("이미 보관함에 저장된 장소입니다.")}
        onReport={() => { if (!selected) return; setSelected(null); router.push({ pathname: "/place-report", params: {
          placeId: selected.result_source === "db" ? String(selected.id) : undefined,
          name: selected.name, address: selected.address,
          lat: Number.isFinite(selected.lat) ? String(selected.lat) : undefined,
          lng: Number.isFinite(selected.lng) ? String(selected.lng) : undefined,
        } }); }} />
      <BottomNav />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  grow: { flex: 1 },
  groupMemo: { minHeight: 84, marginTop: 8, textAlignVertical: "top" },
  actions: { marginTop: 8, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headingRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  addGroup: { minHeight: 40, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", gap: 5, borderRadius: Radius.pill, backgroundColor: Palette.accentSoft },
  addGroupText: { color: Palette.accent, fontSize: 11, fontWeight: "900" },
  groupMaker: { gap: 7 },
  groupRow: { gap: 9, paddingRight: 12 },
  groupTile: { width: 112, height: 112, padding: 13, justifyContent: "space-between", borderWidth: 2, borderColor: "transparent", borderRadius: Radius.medium },
  groupTileSelected: { borderColor: Palette.accent },
  groupTileMint: { backgroundColor: "#DDF4EF" },
  groupTileCoral: { backgroundColor: "#FFD9D3" },
  groupTileLavender: { backgroundColor: "#E6DFFC" },
  groupTileAmber: { backgroundColor: "#FFE5AB" },
  groupTileName: { color: Palette.ink, fontSize: 13, fontWeight: "900" },
  groupCount: { color: Palette.muted, fontSize: 11, fontWeight: "800" },
  selectedHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  settingsButton: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 20, backgroundColor: Palette.surfaceMuted },
  groupSettings: { gap: 8 },
  message: { color: "#0F766E", fontSize: 12, fontWeight: "700" },
  delete: { color: "#B42318", fontSize: 12, fontWeight: "800" },
  section: { gap: 10 },
  placeCard: { gap: 12 },
  placeTop: { flexDirection: "row", alignItems: "center", gap: 12 },
  placePhoto: { borderRadius: 13 },
  placeCopy: { minWidth: 0, flex: 1, gap: 4 },
  placeName: { color: "#222222", fontSize: 15, fontWeight: "900" },
  detailLink: { marginTop: 2, color: Palette.accent, fontSize: 10, fontWeight: "900" },
  memoBox: { minHeight: 54, paddingHorizontal: 11, flexDirection: "row", alignItems: "center", gap: 8, borderRadius: Radius.small, backgroundColor: Palette.surfaceMuted },
  memoLabel: { color: Palette.accent, fontSize: 10, fontWeight: "900" },
  memoInput: { minWidth: 0, flex: 1, paddingVertical: 8, color: Palette.ink, fontSize: 11 },
  memoSave: { paddingHorizontal: 9, paddingVertical: 7, borderRadius: 8, backgroundColor: Palette.surface },
  memoSaveText: { color: Palette.accent, fontSize: 10, fontWeight: "900" },
  placeFooter: { flexDirection: "row", alignItems: "center", gap: 10 },
  emptyGroup: { minHeight: 150, alignItems: "center", justifyContent: "center", gap: 7, borderRadius: Radius.medium, backgroundColor: Palette.surfaceMuted },
  emptyTitle: { color: Palette.ink, fontSize: 13, fontWeight: "900" },
  smallLabel: { marginTop: 12, marginBottom: 6, color: "#59635F", fontSize: 11, fontWeight: "800" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { borderWidth: 1, borderColor: "#DCE4E0", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7 },
  chipActive: { borderColor: "#0F766E", backgroundColor: "#0F766E" },
  chipText: { color: "#59635F", fontSize: 11, fontWeight: "800" },
  chipTextActive: { color: "#FFFFFF" },
});
