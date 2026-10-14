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
  TOGGLE_KEYS,
  type FeatureKey,
  type FeatureRegistry,
  type Features,
} from './features'

/**
 * The registry with every switch handed back to the menu. The codec is tested
 * against this so its cookie behaviour stays proven while the real registry
 * fixes every flag.
 */
const LIVE: FeatureRegistry = Object.fromEntries(
  FEATURE_KEYS.map((k) => [k, { ...FEATURES[k], fixed: undefined }]),
) as FeatureRegistry

describe('features cookie codec', () => {
  test('a missing, empty or malformed cookie is everything on', () => {
    expect(decodeFeaturesCookie(undefined, LIVE)).toEqual(ALL_ON)
    expect(decodeFeaturesCookie('', LIVE)).toEqual(ALL_ON)
    expect(decodeFeaturesCookie('not.a.flag', LIVE)).toEqual(ALL_ON)
  })

  test('lists what is off, in registry order, and round-trips', () => {
    const value = { all_papers: false, stars: true, ask: false }
    expect(encodeFeaturesCookie(value, LIVE)).toBe('all_papers.ask')
    expect(decodeFeaturesCookie('all_papers.ask', LIVE)).toEqual(value)
    // Order and case in the cookie do not matter on the way in.
    expect(decodeFeaturesCookie('ASK. all_papers', LIVE)).toEqual(value)
    for (const key of FEATURE_KEYS) {
      const one = { ...ALL_ON, [key]: false }
      expect(decodeFeaturesCookie(encodeFeaturesCookie(one, LIVE), LIVE)).toEqual(one)
    }
  })

  test('all-on encodes to the empty string, so the write and the absence agree', () => {
    expect(encodeFeaturesCookie(ALL_ON, LIVE)).toBe('')
  })

  test('unknown tokens are ignored, so an old cookie keeps a new flag on', () => {
    expect(decodeFeaturesCookie('all_papers.future_flag', LIVE)).toEqual({
      ...ALL_ON,
      all_papers: false,
    })
  })
})

describe('fixed flags', () => {
  /** What the product is today: Ask hidden, papers list and stars on, no toggles. */
  const TODAY: Features = { all_papers: true, stars: true, ask: false }

  test('the real registry fixes every flag, so the menu has nothing to show', () => {
    expect(FEATURE_KEYS.map((k) => [k, FEATURES[k].fixed])).toEqual([
      ['all_papers', true],
      ['stars', true],
      ['ask', false],
    ])
    expect(TOGGLE_KEYS).toEqual([])
  })

  test('the cookie cannot move a fixed flag, in either direction', () => {
    expect(decodeFeaturesCookie(undefined)).toEqual(TODAY)
    expect(decodeFeaturesCookie('')).toEqual(TODAY)
    // A browser that switched stars off last week gets them back.
    expect(decodeFeaturesCookie('stars')).toEqual(TODAY)
    // A cookie naming only the hidden flags changes nothing either.
    expect(decodeFeaturesCookie('all_papers.ask')).toEqual(TODAY)
  })

  test('a fixed flag is never written, so no stale value waits for the switch to return', () => {
    expect(encodeFeaturesCookie(TODAY)).toBe('')
    expect(encodeFeaturesCookie({ all_papers: false, stars: false, ask: false })).toBe('')
  })

  test('a registry that frees one flag lists exactly that toggle', () => {
    const partly: FeatureRegistry = { ...FEATURES, stars: { ...FEATURES.stars, fixed: undefined } }
    expect(decodeFeaturesCookie('stars', partly)).toEqual({ ...TODAY, stars: false })
    expect(encodeFeaturesCookie({ ...TODAY, stars: false }, partly)).toBe('stars')
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
