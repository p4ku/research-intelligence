import { fixtureWorkspace } from '@/lib/bff/papers/fixtures'
import { describe, expect, test } from 'bun:test'
import { scanTopics } from './topics'

describe('scanTopics', () => {
  test('splits scraper queries into topics', () => {
    expect(scanTopics([fixtureWorkspace])).toEqual(['agentic AI', 'multi-agent systems'])
  })

  test('skips inactive scrapers, strips quotes, dedupes, and caps', () => {
    const topics = scanTopics(
      [
        {
          scrapers: [
            { search_query: '"cold chain" AND (RFID OR sensors)', is_active: true },
            { search_query: 'Cold Chain OR x', is_active: true },
            { search_query: 'never', is_active: false },
            { search_query: 'perovskite; batteries', is_active: true },
          ],
        },
      ],
      3,
    )
    expect(topics).toEqual(['cold chain', 'RFID', 'sensors'])
  })

  test('drops arXiv field syntax: prefixes go, category clauses are not topics', () => {
    expect(
      scanTopics([
        {
          scrapers: [
            {
              search_query: 'cat:cs.AI AND all:machine learning OR ti:"neural network"',
              is_active: true,
            },
          ],
        },
      ]),
    ).toEqual(['machine learning', 'neural network'])
  })
})
