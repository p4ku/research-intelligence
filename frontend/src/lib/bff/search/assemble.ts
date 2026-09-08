/**
 * Corpus + query → SearchResponse. The whole of search, minus the fetching:
 * pure so the tests can drive it with fixtures, and so the service stays a
 * one-liner around the cached corpus.
 */
import { parseQuery, rankAll, snippet, tokenize, type Query } from '@/lib/search/match'
import { editionHref } from '../briefings/href'
import { PASSED_STATUSES, type ScoredPaper } from '../papers/schema'
import type { WorkspaceSummary } from '../workspaces/schema'
import type { SearchDomain, SearchHit, SearchQuery, SearchResponse } from './schema'

export interface SearchCorpus {
  workspaces: WorkspaceSummary[]
  papers: ScoredPaper[]
  /** workspace id → its newest edition (day and run), or null with no edition yet. */
  latestEdition: Record<string, LatestEdition | null>
}

export interface LatestEdition {
  /** YYYY-MM-DD */
  date: string
  runId: string
}

const SNIPPET_LENGTH = 160
const MAX_DOMAINS = 3
/** A screened-through paper wins a near-tie against a rejected one; a strong hit still surfaces either way. */
const PASSED_BONUS = 10

export function askHref(question: string, paperId: string): string {
  return `/ask?q=${encodeURIComponent(question)}&paper=${paperId}`
}

function empty(query: string, intent: SearchResponse['intent']): SearchResponse {
  return {
    query,
    intent,
    papers: [],
    papers_total: 0,
    papers_hidden_by_screening: 0,
    domains: [],
    ask: null,
    id: null,
    exact: null,
  }
}

function toHit(
  paper: ScoredPaper,
  workspaceName: string,
  tokens: string[],
  matched: SearchHit['matched'],
  score: number,
): SearchHit {
  return {
    id: paper.id,
    title: paper.title,
    authors: paper.authors,
    first_author: paper.authors[0] ?? null,
    signal_score: paper.signal_score,
    workspace_id: paper.workspace_id,
    workspace_name: workspaceName,
    screening_status: paper.screening_status,
    created_at: paper.created_at,
    snippet: snippet(paper.abstract, tokens, SNIPPET_LENGTH),
    matched,
    score,
  }
}

const stripVersion = (arxivId: string) => arxivId.toLowerCase().replace(/v\d+$/, '')

function findExact(papers: ScoredPaper[], id: { kind: 'arxiv' | 'doi'; value: string }) {
  return papers.find((p) =>
    id.kind === 'arxiv'
      ? p.arxiv_id !== null && stripVersion(p.arxiv_id) === id.value
      : p.doi !== null && p.doi.toLowerCase() === id.value,
  )
}

function matchingDomains(
  corpus: SearchCorpus,
  query: Query,
  matchedByWorkspace: Map<string, number>,
): SearchDomain[] {
  const rows: SearchDomain[] = []
  for (const ws of corpus.workspaces) {
    const words = tokenize(ws.name)
    const hit = query.tokens.some((token) =>
      words.some((word) => word === token || word.startsWith(token)),
    )
    if (!hit) continue
    const latest = corpus.latestEdition[ws.id] ?? null
    rows.push({
      id: ws.id,
      name: ws.name,
      papers_matched: matchedByWorkspace.get(ws.id) ?? 0,
      latest_edition: latest
        ? { date: latest.date, href: editionHref(latest.date, ws.id, { runId: latest.runId }) }
        : null,
    })
  }
  return rows.sort((a, b) => b.papers_matched - a.papers_matched).slice(0, MAX_DOMAINS)
}

export function assembleSearch(corpus: SearchCorpus, { q, limit }: SearchQuery): SearchResponse {
  const query = parseQuery(q)
  const names = new Map(corpus.workspaces.map((ws) => [ws.id, ws.name]))
  const nameOf = (id: string) => names.get(id) ?? ''

  if (query.intent.kind === 'empty') return empty(q, 'empty')

  if (query.intent.kind === 'id') {
    const { id } = query.intent
    const paper = findExact(corpus.papers, id)
    const response = empty(q, 'id')
    response.id = id
    if (!paper) return response
    const hit = toHit(paper, nameOf(paper.workspace_id), query.tokens, ['id'], 100)
    return {
      ...response,
      papers: [hit],
      papers_total: 1,
      papers_hidden_by_screening: PASSED_STATUSES.includes(paper.screening_status) ? 0 : 1,
      ask: { href: askHref(q, paper.id), question: q, paper_id: paper.id },
      exact: { paper_id: paper.id },
    }
  }

  const ranked = rankAll(corpus.papers, query).map(({ paper, hit }) => ({
    paper,
    score: hit.score + (PASSED_STATUSES.includes(paper.screening_status) ? PASSED_BONUS : 0),
    matched: hit.matched,
  }))
  ranked.sort(
    (a, b) =>
      b.score - a.score ||
      b.paper.created_at.localeCompare(a.paper.created_at) ||
      a.paper.id.localeCompare(b.paper.id),
  )

  const matchedByWorkspace = new Map<string, number>()
  let hidden = 0
  for (const { paper } of ranked) {
    matchedByWorkspace.set(
      paper.workspace_id,
      (matchedByWorkspace.get(paper.workspace_id) ?? 0) + 1,
    )
    if (!PASSED_STATUSES.includes(paper.screening_status)) hidden += 1
  }

  const papers = ranked
    .slice(0, limit)
    .map(({ paper, score, matched }) =>
      toHit(paper, nameOf(paper.workspace_id), query.tokens, matched, score),
    )
  const top = papers[0]

  return {
    query: q,
    intent: query.intent.kind,
    papers,
    papers_total: ranked.length,
    papers_hidden_by_screening: hidden,
    domains: matchingDomains(corpus, query, matchedByWorkspace),
    ask: top ? { href: askHref(q, top.id), question: q, paper_id: top.id } : null,
    id: null,
    exact: null,
  }
}
