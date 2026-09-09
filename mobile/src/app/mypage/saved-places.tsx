import { recommendationApi } from "@/api/recommendations";
import { useAuth } from "@/auth/auth-context";
import { BottomNav } from "@/components/bottom-nav";
import { LoadState } from "@/components/load-state";
import { INPUT_PLACEHOLDER_COLOR, Screen, ui } from "@/components/screen";
import { useResource } from "@/hooks/use-resource";
import { useMemo, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

type SavedPlaceGroup = {
  id: number;
  name: string;
  memo?: string;
};

type SavedPlace = {
  id: number;
  name?: string;
  place_name?: string;
  address?: string;
  memo?: string;
  group_id?: number | null;
  group_name?: string;
};

export default function SavedPlacesScreen() {
  const { ready, isLoggedIn } = useAuth();
  const [groups, setGroups] = useState<SavedPlaceGroup[]>([]);
  const [places, setPlaces] = useState<SavedPlace[]>([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [groupNameDrafts, setGroupNameDrafts] = useState<Record<number, string>>({});
  const [groupMemoDrafts, setGroupMemoDrafts] = useState<Record<number, string>>({});
  const [placeMemoDrafts, setPlaceMemoDrafts] = useState<Record<number, string>>({});
  const [busyKey, setBusyKey] = useState("");
  const [message, setMessage] = useState("");

  const load = async () => {
    const [groupResponse, placeResponse] = await Promise.all([
      recommendationApi.savedPlaceGroups(),
      recommendationApi.savedPlaces({ page: 1, page_size: 100 }),
    ]);
    setGroups((groupResponse as { results?: SavedPlaceGroup[] }).results || []);
    setPlaces((placeResponse as { results?: SavedPlace[] }).results || []);
  };
  const { loading, error, reload } = useResource(load, undefined, ready && isLoggedIn);

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
    <View key={place.id} style={ui.card}>
      <View style={styles.actions}>
        <Text style={styles.placeName}>{place.place_name || place.name || "이름 없는 장소"}</Text>
        <Pressable onPress={() => deletePlace(place)}>
          <Text style={styles.delete}>장소 삭제</Text>
        </Pressable>
      </View>
      {place.address ? <Text style={ui.muted}>{place.address}</Text> : null}
      <Text style={styles.smallLabel}>그룹 선택</Text>
      <View style={styles.chips}>
        <Pressable
          onPress={() => movePlace(place, null)}
          style={[styles.chip, !place.group_id && styles.chipActive]}
        >
          <Text style={[styles.chipText, !place.group_id && styles.chipTextActive]}>미분류</Text>
        </Pressable>
        {groups.map((group) => (
          <Pressable
            key={group.id}
            onPress={() => movePlace(place, group.id)}
            style={[styles.chip, place.group_id === group.id && styles.chipActive]}
          >
            <Text style={[styles.chipText, place.group_id === group.id && styles.chipTextActive]}>
              {group.name}
            </Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.row}>
        <TextInput
          value={placeMemoDrafts[place.id] ?? place.memo ?? ""}
          onChangeText={(value) => setPlaceMemoDrafts((current) => ({ ...current, [place.id]: value }))}
          placeholder="이 장소에 대한 메모"
          placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
          multiline
          style={[ui.input, styles.grow]}
        />
        <Pressable onPress={() => savePlaceMemo(place)} style={ui.buttonSecondary}>
          <Text style={ui.buttonSecondaryText}>메모 저장</Text>
        </Pressable>
      </View>
    </View>
  );

  return (
    <View style={styles.root}>
      <Screen title="장소 보관함" subtitle="원하는 그룹으로 나누고 메모를 남겨 보세요.">
        <LoadState loading={loading} error={error} retry={reload} />
        {!loading && !error ? (
          <>
            <View style={ui.card}>
              <Text style={ui.sectionTitle}>새 그룹</Text>
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
            </View>

            {message ? <Text style={styles.message}>{message}</Text> : null}

            <Text style={ui.sectionTitle}>내 그룹 {groups.length}</Text>
            {groups.length ? groups.map((group) => (
              <View key={group.id} style={ui.card}>
                <TextInput
                  value={groupNameDrafts[group.id] ?? group.name}
                  onChangeText={(value) => setGroupNameDrafts((current) => ({ ...current, [group.id]: value }))}
                  placeholder="그룹 이름"
                  placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                  maxLength={100}
                  style={ui.input}
                />
                <TextInput
                  value={groupMemoDrafts[group.id] ?? group.memo ?? ""}
                  onChangeText={(value) => setGroupMemoDrafts((current) => ({ ...current, [group.id]: value }))}
                  placeholder="이 그룹에 대한 메모"
                  placeholderTextColor={INPUT_PLACEHOLDER_COLOR}
                  multiline
                  style={[ui.input, styles.groupMemo]}
                />
                <View style={styles.actions}>
                  <Pressable onPress={() => saveGroup(group)} style={ui.buttonSecondary}>
                    <Text style={ui.buttonSecondaryText}>이름·메모 저장</Text>
                  </Pressable>
                  <Pressable onPress={() => deleteGroup(group)}>
                    <Text style={styles.delete}>그룹 삭제</Text>
                  </Pressable>
                </View>
              </View>
            )) : <Text style={ui.muted}>아직 만든 그룹이 없습니다.</Text>}

            {[{ id: null, name: "미분류" } as const, ...groups].map((group) => {
              const groupedPlaces = placesByGroup.get(group.id) || [];
              return (
                <View key={group.id ?? "ungrouped"} style={styles.section}>
                  <Text style={ui.sectionTitle}>{group.name} {groupedPlaces.length}</Text>
                  {groupedPlaces.length
                    ? groupedPlaces.map(renderPlace)
                    : <Text style={ui.muted}>이 그룹에 저장된 장소가 없습니다.</Text>}
                </View>
              );
            })}
          </>
        ) : null}
      </Screen>
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
  message: { color: "#0F766E", fontSize: 12, fontWeight: "700" },
  delete: { color: "#B42318", fontSize: 12, fontWeight: "800" },
  section: { gap: 8 },
  placeName: { color: "#222222", fontSize: 15, fontWeight: "900" },
  smallLabel: { marginTop: 12, marginBottom: 6, color: "#59635F", fontSize: 11, fontWeight: "800" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { borderWidth: 1, borderColor: "#DCE4E0", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7 },
  chipActive: { borderColor: "#0F766E", backgroundColor: "#0F766E" },
  chipText: { color: "#59635F", fontSize: 11, fontWeight: "800" },
  chipTextActive: { color: "#FFFFFF" },
});
