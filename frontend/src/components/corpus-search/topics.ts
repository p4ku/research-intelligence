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

export function scanTopics(workspaces: readonly TopicSource[], max = MAX_TOPICS): string[] {
  const seen = new Set<string>()
  const topics: string[] = []
  for (const ws of workspaces) {
    for (const scraper of ws.scrapers) {
      if (!scraper.is_active) continue
      for (const part of scraper.search_query.split(SPLIT)) {
        const topic = part.replace(NOISE, '').replace(/\s+/g, ' ').trim()
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
