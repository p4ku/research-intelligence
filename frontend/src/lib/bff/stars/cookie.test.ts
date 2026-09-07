import { describe, expect, test } from 'bun:test'
import { capStars, decodeStarsCookie, encodeStarsCookie, STARS_CAP } from './cookie'
import { applyStar, emptyStars } from './schema'

const paper = '8c9a1a2e-5b1d-4c0e-9d5a-7f1e3b2c4d5e'
const run = '00000000-0000-4000-8000-000000000031'

describe('stars cookie codec', () => {
  test('round-trips both lists', () => {
    const value = { papers: [paper], briefings: [run] }
    expect(decodeStarsCookie(encodeStarsCookie(value))).toEqual(value)
  })

  test('a missing or malformed cookie is nothing starred', () => {
    expect(decodeStarsCookie(undefined)).toEqual(emptyStars)
    expect(decodeStarsCookie('not a cookie we wrote')).toEqual(emptyStars)
    // A damaged id drops out; the rest survive.
    const one = encodeStarsCookie({ papers: [paper], briefings: [run] })
    expect(decodeStarsCookie(`zz.${one}`)).toEqual({ papers: [paper], briefings: [run] })
    // Sixteen bytes that are not an RFC UUID (bad version nibble) never reach the contract.
    const crafted = Buffer.from('11111111111111111111111111111111', 'hex').toString('base64url')
    expect(decodeStarsCookie(`${crafted}~`)).toEqual(emptyStars)
  })

  test('stays under a 4 KB cookie at the cap', () => {
    const uuid = (i: number) => `${i.toString(16).padStart(8, '0')}-0000-4000-8000-000000000000`
    const full = {
      papers: Array.from({ length: 200 }, (_, i) => uuid(i)),
      briefings: Array.from({ length: 100 }, (_, i) => uuid(1000 + i)),
    }
    const encoded = encodeStarsCookie(full)
    expect(encoded.length).toBeLessThan(4000)
    const kept = decodeStarsCookie(encoded)
    expect(kept.papers).toHaveLength(STARS_CAP.papers)
    expect(kept.briefings).toHaveLength(STARS_CAP.briefings)
    // Newest (last) survive the cap.
    expect(kept.papers.at(-1)).toBe(uuid(199))
  })

  test('capStars drops the oldest first', () => {
    const ids = Array.from(
      { length: STARS_CAP.papers + 2 },
      (_, i) => `${i.toString(16).padStart(8, '0')}-0000-4000-8000-000000000000`,
    )
    expect(capStars({ papers: ids, briefings: [] }).papers[0]).toBe(ids[2])
  })
})

describe('applyStar', () => {
  test('stars once, moves a re-star to the end, unstars cleanly', () => {
    const a = applyStar(emptyStars, { kind: 'paper', id: paper, starred: true })
    expect(a.papers).toEqual([paper])
    const b = applyStar(a, { kind: 'paper', id: run, starred: true })
    const c = applyStar(b, { kind: 'paper', id: paper, starred: true })
    expect(c.papers).toEqual([run, paper])
    expect(applyStar(c, { kind: 'paper', id: paper, starred: false }).papers).toEqual([run])
    expect(applyStar(c, { kind: 'briefing', id: run, starred: true }).briefings).toEqual([run])
  })
})
