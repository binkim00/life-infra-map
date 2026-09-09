import { Pressable, Text, View } from "react-native";
import { ui } from "./screen";
export function Pagination({ page, setPage, hasNext, loading }: { page: number; setPage: (value: number) => void; hasNext: boolean; loading: boolean }) {
  return <View style={ui.row}>
    <Pressable disabled={loading || page <= 1} onPress={() => setPage(page - 1)} style={ui.buttonSecondary}><Text>이전</Text></Pressable>
    <Text style={ui.muted}>{page}페이지</Text>
    <Pressable disabled={loading || !hasNext} onPress={() => setPage(page + 1)} style={ui.buttonSecondary}><Text>다음</Text></Pressable>
  </View>;
}
