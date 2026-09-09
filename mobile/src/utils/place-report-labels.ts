const STATUS_LABELS: Record<string, string> = {
  pending: "검토 대기",
  approved: "승인",
  rejected: "반려",
};

const TYPE_LABELS: Record<string, string> = {
  new_place: "새 장소",
  tag_addition: "태그 추가",
  tag_suggestion: "태그 추가",
  correction: "정보 수정",
  edit_place: "정보 수정",
};

export const placeReportStatusLabel = (status?: string, serverLabel?: string) =>
  serverLabel || (status ? STATUS_LABELS[status] || status : "접수");

export const placeReportTypeLabel = (type?: string, serverLabel?: string) =>
  serverLabel || (type ? TYPE_LABELS[type] || type : "제보");
