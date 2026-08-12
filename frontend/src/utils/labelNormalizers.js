/**
 * 백엔드가 라벨을 문자열로도, {label|name|value} 객체로도 내려줍니다.
 * 검색 기록/선호 화면이 같은 규칙으로 읽고 있어 한곳에 모아 둡니다.
 */
export const normalizeLabelValue = (item) => {
  if (typeof item === 'string') return item.trim()
  if (typeof item === 'number' && Number.isFinite(item)) return String(item)
  if (!item || typeof item !== 'object') return ''

  const labelKeys = ['label', 'name', 'display_name', 'displayName', 'value', 'text']
  for (const key of labelKeys) {
    const label = normalizeLabelValue(item[key])
    if (label) return label
  }

  return ''
}

export const normalizeLabelList = (items) => {
  if (!Array.isArray(items)) return []

  return [...new Set(
    items
      .map(normalizeLabelValue)
      .filter((item) => item && item !== '[object Object]'),
  )]
}
