/**
 * Copy-layer guarantees (error-UX audit #6):
 *  - every catalogued problem slug maps to a product sentence, in en and de
 *  - no sentence leaks internals (Django, /api/, exceptions, status codes)
 *  - only `/problems/validation` may surface `detail`
 *  - errorsFromSubmit never returns an empty map (the never-silent invariant)
 */
import { describe, expect, test } from 'bun:test'
import { de } from '../../locales/de'
import { makeT } from '../i18n'
import { problem, PROBLEM_SLUGS, problemBody, type Problem } from './core/problem'
import { errorsFromSubmit, PROBLEM_COPY, problemMessage } from './problem-copy'

const tEn = makeT('en')
const tDe = makeT('de')

// Internals that must never reach a user-facing sentence.
const FORBIDDEN = /Django|\/api\/|\bBFF\b|TypeError|Error:|HTTP \d|\b[45]\d\d\b/

describe('problemMessage', () => {
  test('every catalogued slug has copy in en and de, free of internals', () => {
    for (const slug of PROBLEM_SLUGS) {
      const en = problemMessage(problemBody(slug), tEn)
      expect(en.length).toBeGreaterThan(0)
      expect(en).not.toMatch(FORBIDDEN)
      // The de entry must exist (dynamic t() calls escape the static i18n scan).
      const source = PROBLEM_COPY[slug]
      expect(de[source]).toBeDefined()
      expect(de[source]).not.toMatch(FORBIDDEN)
      expect(problemMessage(problemBody(slug), tDe)).toBe(de[source])
    }
  })

  test('validation detail (human-written) passes through', () => {
    const p = problemBody('validation', { detail: 'Old password is incorrect.' })
    expect(problemMessage(p, tEn)).toBe('Old password is incorrect.')
  })

  test('non-validation detail (operator material) never shows', () => {
    const p = problemBody('upstream-unavailable', {
      detail: 'Django did not respond (/api/papers/).',
    })
    expect(problemMessage(p, tEn)).not.toContain('Django')
    expect(problemMessage(p, tEn)).not.toContain('/api/')
  })

  test('unknown type and missing problem fall back to product copy', () => {
    expect(problemMessage({ type: '/problems/new-slug', title: 'X', status: 418 }, tEn)).toBe(
      'Something went wrong. Try again.',
    )
    expect(problemMessage(null, tEn)).toBe('Something went wrong. Try again.')
  })

  test('a wire body that is not a problem falls back instead of throwing', () => {
    // What a proxy or CDN error page looks like once `res.json()` succeeds.
    const proxyBody = { error: 'bad gateway', status: 502 } as unknown as Problem
    expect(problemMessage(proxyBody, tEn)).toBe('Something went wrong. Try again.')
    expect(problemMessage('upstream error' as unknown as Problem, tEn)).toBe(
      'Something went wrong. Try again.',
    )
  })
})

describe('errorsFromSubmit', () => {
  const FIELDS = ['first_name', 'last_name', 'email', 'username'] as const
  const FALLBACK = "Couldn't save your profile. Try again."

  test('rendered field keys paint their fields', () => {
    const errors = errorsFromSubmit(
      problem('validation', { errors: { email: ['Enter a valid email address.'] } }),
      FIELDS,
      tEn,
      FALLBACK,
    )
    expect(errors).toEqual({ email: 'Enter a valid email address.' })
  })

  test('DRF non_field_errors and zod (root) fold into _, never vanish', () => {
    for (const key of ['non_field_errors', '(root)']) {
      const errors = errorsFromSubmit(
        problem('validation', { errors: { [key]: ['Passwords do not match.'] } }),
        FIELDS,
        tEn,
        FALLBACK,
      )
      expect(errors._).toBe('Passwords do not match.')
    }
  })

  test('an upstream-shape errors map never marks a field invalid', () => {
    const errors = errorsFromSubmit(
      problem('upstream-shape', { errors: { email: ['Expected string, got null'] } }),
      FIELDS,
      tEn,
      FALLBACK,
    )
    expect(errors.email).toBeUndefined()
    expect(errors._).toBeDefined()
  })

  test('never silent: every thrown shape yields a non-empty map', () => {
    const thrown: unknown[] = [
      problem('validation'),
      problem('validation', { errors: {} }),
      problem('upstream-error'),
      { problem: problemBody('internal') }, // BffClientError across module instances
      new TypeError('Failed to fetch'),
      'not even an Error',
    ]
    for (const error of thrown) {
      const errors = errorsFromSubmit(error, FIELDS, tEn, FALLBACK)
      expect(Object.values(errors).some((v) => v.length > 0)).toBe(true)
    }
  })

  test('a raw exception shows the fallback, not String(error)', () => {
    const errors = errorsFromSubmit(new TypeError('Failed to fetch'), FIELDS, tEn, FALLBACK)
    expect(errors._).toBe(FALLBACK)
  })
})
