export const NO_RESULT_MESSAGE_PATTERNS = [
  '검색 결과가 없습니다',
  '추천 결과가 없습니다',
  '조건에 맞는 추천 결과가 없습니다',
  '후보를 찾지 못했습니다',
]

export const RESULT_FILTER_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: 'db', label: '저장 장소' },
  { value: 'kakao', label: '카카오' },
  { value: 'web', label: '웹 참고' },
]

export const RESULT_SORT_OPTIONS = [
  { value: 'recommendation', label: '추천순' },
  { value: 'distance', label: '거리순' },
  { value: 'confidence', label: '신뢰도순' },
]

export const AI_SEARCH_PRESETS = [
  {
    label: '조용히 작업할 곳',
    query: '조용히 작업하기 좋은 카페',
  },
  {
    label: '잠깐 쉴 곳',
    query: '잠깐 쉴 곳',
  },
  {
    label: '산책/힐링',
    query: '산책하고 힐링하기 좋은 곳',
  },
  {
    label: '흡연 가능한 곳',
    query: '흡연 가능한 곳',
  },
  {
    label: '근처 화장실',
    query: '근처 화장실 찾아줘',
  },
  {
    label: '가까운 편의점',
    query: '가까운 편의점 찾아줘',
  },
  {
    label: '근처 약국',
    query: '근처 약국 찾아줘',
  },
  {
    label: '주차장',
    query: '근처 주차장 찾아줘',
  },
  {
    label: '주변 공원',
    query: '주변 공원 찾아줘',
  },
]
