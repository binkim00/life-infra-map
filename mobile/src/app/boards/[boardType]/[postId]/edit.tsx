import { useLocalSearchParams } from "expo-router";
import { PostEditor } from "@/components/post-editor";
export default function BoardEditScreen() {
  const { boardType = "free", postId = "" } = useLocalSearchParams<{
    boardType: string;
    postId: string;
  }>();
  return <PostEditor boardType={boardType} postId={postId} />;
}
