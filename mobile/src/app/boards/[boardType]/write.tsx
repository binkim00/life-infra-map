import { useLocalSearchParams } from "expo-router";
import { PostEditor } from "@/components/post-editor";
export default function BoardWriteScreen() {
  const { boardType = "free" } = useLocalSearchParams<{ boardType: string }>();
  return <PostEditor boardType={boardType} />;
}
