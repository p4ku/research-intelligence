/**
 * "Try" suggestions for an empty field: the domains' own scan topics, read
 * off their scraper queries ("agentic AI OR multi-agent systems" → two
 * topics). What the scan looks for is what the corpus can answer. Pure.
 */
export interface TopicSource {
  scrapers: { search_query: string; is_active: boolean }[]
}

const MAX_TOPICS = 3
const SPLIT = /\s+(?:OR|AND|NOT)\s+|\s*[|,;]\s*/i
const NOISE = /["'()[\]*]/g
/** arXiv field prefixes ("all:", "ti:", "abs:", "au:") are syntax, not topic. */
const FIELD_PREFIX = /^(?:all|ti|abs|au|co|jr|rn):\s*/i
/** Category and id clauses ("cat:cs.AI", "id:…") name no topic at all. */
const NOT_A_TOPIC = /^(?:cat|id|submittedDate):/i

export function scanTopics(workspaces: readonly TopicSource[], max = MAX_TOPICS): string[] {
  const seen = new Set<string>()
  const topics: string[] = []
  for (const ws of workspaces) {
    for (const scraper of ws.scrapers) {
      if (!scraper.is_active) continue
      for (const part of scraper.search_query.split(SPLIT)) {
        const clause = part.replace(NOISE, '').replace(/\s+/g, ' ').trim()
        if (NOT_A_TOPIC.test(clause)) continue
        const topic = clause.replace(FIELD_PREFIX, '')
        const key = topic.toLowerCase()
        if (topic.length < 3 || topic.length > 60 || seen.has(key)) continue
        seen.add(key)
        topics.push(topic)
        if (topics.length >= max) return topics
      }
    }
  }
  return topics
}
