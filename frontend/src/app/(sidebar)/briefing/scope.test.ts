import { describe, expect, test } from 'bun:test'
import { domainNames, domainScope, runScope } from './scope'

const MINE = [
  { id: '00000000-0000-4000-8000-000000000001', name: 'Agentic AI' },
  { id: '00000000-0000-4000-8000-000000000002', name: 'Hybrid Computing' },
]

describe('domainScope', () => {
  test('one of the user’s domains, by id', () => {
    expect(domainScope(MINE, MINE[1]!.id)).toBe(MINE[1]!.id)
  })

  test('anything else falls back to "every domain" rather than a 404', () => {
    expect(domainScope(MINE, undefined)).toBeUndefined()
    expect(domainScope(MINE, '')).toBeUndefined()
    expect(domainScope(MINE, 'not-a-uuid')).toBeUndefined()
    // A well-formed id the user has since left, or never had.
    expect(domainScope(MINE, '00000000-0000-4000-8000-000000000099')).toBeUndefined()
  })
})

describe('runScope', () => {
  test('a well-formed run id passes through; whether it exists is the service’s question', () => {
    expect(runScope('00000000-0000-4000-8000-000000000101')).toBe(
      '00000000-0000-4000-8000-000000000101',
    )
  })

  test('a malformed run means "the day’s newest", never an error', () => {
    expect(runScope(undefined)).toBeUndefined()
    expect(runScope('')).toBeUndefined()
    expect(runScope('nope')).toBeUndefined()
    expect(runScope('00000000-0000-4000-8000-00000000010')).toBeUndefined()
  })
})

describe('domainNames', () => {
  test('names by id, for crumbs and badges', () => {
    expect(domainNames(MINE)).toEqual({
      [MINE[0]!.id]: 'Agentic AI',
      [MINE[1]!.id]: 'Hybrid Computing',
    })
  })
})
