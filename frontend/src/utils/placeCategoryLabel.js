const CATEGORY_LABELS = {
  cafe: '카페', restaurant: '음식점', convenience_store: '편의점',
  shopping: '쇼핑', parking: '주차장', toilet: '화장실',
  freewifi: '무료 와이파이', smoking_area: '흡연구역', shelter: '쉼터',
  city_park: '공원', tourism: '관광지', beach: '해수욕장',
  pharmacy: '약국', hospital: '병원', library: '도서관',
}

export const placeCategoryLabel = (place) => {
  const explicit = place?.category_label || place?.categoryLabel
  if (explicit) return explicit
  const category = String(place?.category || '').trim()
  return CATEGORY_LABELS[category] || (category.includes('_') ? '기타 장소' : category)
}
