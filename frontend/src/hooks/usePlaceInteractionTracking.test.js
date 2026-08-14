import { describe, expect, it } from 'vitest'

import {
  getFeedbackTagOptions,
  normalizeRequestedTags,
} from './usePlaceInteractionTracking'


describe('place interaction tag helpers', () => {
  it('normalizes and deduplicates requested tags', () => {
    expect(normalizeRequestedTags([
      '#조용한',
      { label: '브런치' },
      '조용한',
      '',
    ])).toEqual(['조용한', '브런치'])
  })

  it('prioritizes requested tags and adds category defaults', () => {
    const options = getFeedbackTagOptions(
      { category: '카페' },
      ['브런치', '분위기 좋은'],
    )

    expect(options[0]).toEqual({ tag: '브런치', label: '브런치' })
    expect(options.map((option) => option.tag)).toContain('조용한')
    expect(options.map((option) => option.tag)).toContain('작업하기 좋은')
  })
})
