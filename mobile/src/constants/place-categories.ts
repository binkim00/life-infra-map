export const PLACE_CATEGORIES = [
  { value: "cafe", label: "카페" },
  { value: "restaurant", label: "음식점" },
  { value: "convenience_store", label: "편의점" },
  { value: "shopping", label: "쇼핑" },
  { value: "parking", label: "주차장" },
  { value: "toilet", label: "화장실" },
  { value: "freewifi", label: "무료 와이파이" },
  { value: "smoking_area", label: "흡연구역" },
  { value: "shelter", label: "쉼터" },
  { value: "city_park", label: "공원" },
  { value: "tourism", label: "관광지" },
  { value: "beach", label: "해수욕장" },
  { value: "pharmacy", label: "약국" },
  { value: "hospital", label: "병원" },
  { value: "library", label: "도서관" },
] as const;

export const normalizePlaceCategory = (value?: string) => {
  const trimmed = value?.trim() || "";
  return (
    PLACE_CATEGORIES.find(
      (category) =>
        category.value === trimmed || category.label === trimmed,
    )?.value || ""
  );
};

export const placeCategoryLabel = (value?: string) =>
  PLACE_CATEGORIES.find(
    (category) =>
      category.value === value || category.label === value,
  )?.label || value || "미선택";
