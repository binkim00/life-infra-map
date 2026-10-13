import { describe, expect, it } from 'vitest'
import { placeCategoryLabel } from './placeCategoryLabel'

describe('placeCategoryLabel', () => {
  it('shows known category codes as Korean names and keeps provider labels', () => {
    expect(placeCategoryLabel({ category: 'cafe' })).toBe('카페')
    expect(placeCategoryLabel({ category: 'smoking_area' })).toBe('흡연구역')
    expect(placeCategoryLabel({ category: 'cafe', category_label: '커피전문점' })).toBe('커피전문점')
    expect(placeCategoryLabel({ category: '음식점 > 한식' })).toBe('음식점 > 한식')
  })
  it('does not expose an unknown snake case code', () => {
    expect(placeCategoryLabel({ category: 'future_category' })).toBe('기타 장소')
  })
})
