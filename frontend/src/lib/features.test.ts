import { describe, expect, test } from 'bun:test'
import { de } from '../locales/de'
import {
  ALL_ON,
  decodeFeaturesCookie,
  encodeFeaturesCookie,
  FEATURE_KEYS,
  featureOwning,
  FEATURES,
  isVisible,
  type FeatureKey,
} from './features'

describe('features cookie codec', () => {
  test('a missing, empty or malformed cookie is everything on', () => {
    expect(decodeFeaturesCookie(undefined)).toEqual(ALL_ON)
    expect(decodeFeaturesCookie('')).toEqual(ALL_ON)
    expect(decodeFeaturesCookie('not.a.flag')).toEqual(ALL_ON)
  })

  test('lists what is off, in registry order, and round-trips', () => {
    const value = { all_papers: false, stars: true, ask: false }
    expect(encodeFeaturesCookie(value)).toBe('all_papers.ask')
    expect(decodeFeaturesCookie('all_papers.ask')).toEqual(value)
    // Order and case in the cookie do not matter on the way in.
    expect(decodeFeaturesCookie('ASK. all_papers')).toEqual(value)
    for (const key of FEATURE_KEYS) {
      const one = { ...ALL_ON, [key]: false }
      expect(decodeFeaturesCookie(encodeFeaturesCookie(one))).toEqual(one)
    }
  })

  test('all-on encodes to the empty string, so the write and the absence agree', () => {
    expect(encodeFeaturesCookie(ALL_ON)).toBe('')
  })

  test('unknown tokens are ignored, so an old cookie keeps a new flag on', () => {
    expect(decodeFeaturesCookie('all_papers.future_flag')).toEqual({ ...ALL_ON, all_papers: false })
  })
})

describe('nav filtering and route ownership', () => {
  test('isVisible hides only tagged items whose flag is off', () => {
    const off = { ...ALL_ON, ask: false }
    const nav: { href: string; feature?: FeatureKey }[] = [
      { href: '/dashboard' },
      { href: '/papers', feature: 'all_papers' },
      { href: '/ask', feature: 'ask' },
    ]
    expect(nav.filter((item) => isVisible(item, off)).map((i) => i.href)).toEqual([
      '/dashboard',
      '/papers',
    ])
  })

  test('the list flag owns /papers but not a paper', () => {
    expect(featureOwning('/papers')).toBe('all_papers')
    expect(featureOwning('/papers/8c9a1a2e')).toBeUndefined()
    expect(featureOwning('/ask')).toBe('ask')
    expect(featureOwning('/dashboard')).toBeUndefined()
  })
})

describe('registry labels', () => {
  // Labels reach t() dynamically, so the static i18n guard cannot see them.
  test('every toggle label and the menu heading have a German translation', () => {
    const keys = [
      'Demo features',
      ...Object.values(FEATURES).map((d) => (d.ctx ? `${d.ctx}|${d.label}` : d.label)),
    ]
    expect(keys.filter((k) => !(k in de))).toEqual([])
  })
})
