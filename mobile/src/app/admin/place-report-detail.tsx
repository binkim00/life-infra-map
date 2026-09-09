import { useLocalSearchParams } from "expo-router";
import { ReportDetail } from "@/components/report-detail";
export default function AdminReportDetail() {
  const { id = "" } = useLocalSearchParams<{ id: string }>();
  return <ReportDetail id={id} admin />;
}
