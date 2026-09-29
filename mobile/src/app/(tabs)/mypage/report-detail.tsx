import { useLocalSearchParams } from "expo-router";
import { ReportDetail } from "@/components/report-detail";
export default function MyReportDetail() {
  const { id = "", receipt } = useLocalSearchParams<{ id: string; receipt?: string }>();
  return <ReportDetail id={id} receipt={receipt === "1"} />;
}
