# search

## Purpose

The Home typeahead: one field, every paper the user can see. It reads a
query the way a researcher typed it — a topic, a half-remembered title, an
author, an arXiv id or DOI (or a pasted arxiv.org / doi.org URL), a domain
name, or a question — and answers with ranked papers, matching domains and
an Ask action scoped to the top hit.

## BFF route

| Route             | Query                                                       | Returns          |
| ----------------- | ----------------------------------------------------------- | ---------------- |
| `GET /bff/search` | `q` (≤ 200 chars; empty allowed), `limit` (1–20, default 8) | `SearchResponse` |

Not paginated: the "See all N papers" row hands off to
`/bff/papers?search=`, which is. An empty `q` is valid and returns an empty
response — the field fires one on focus to warm the corpus cache.

Schemas: `src/lib/bff/search/schema.ts`. Errors are problem+json.

## How it is built

- **Matcher**: `src/lib/search/match.ts` — shared with the Papers page
  filter and `/bff/papers?search=`, so the dropdown and Papers agree.
  Tokenised AND matching with prefixes, hyphen ≡ space, title > authors >
  abstract > id weights, signal score as a tie-breaker, id and question
  intent detection.
- **Assembly**: `src/lib/bff/search/assemble.ts` — pure; the tests drive
  it with the paper fixtures. Screened-through papers get a small bonus so
  they win near-ties against rejected ones.
- **Corpus cache**: `src/lib/bff/search/corpus.ts` — `papers.listEverywhere()`
  plus the newest edition date per domain, held 45 s per user, keyed on a
  hash of the access token. Cleared when a run starts
  (`/bff/pipeline-runs/start`); a run _finishing_ is only seen after the TTL.
  Bound: 32 users × one corpus. Only search reads it.

## Source

`search` is composed only (`BFF_SOURCE_SEARCH=composed`) and follows the
papers / workspaces / briefings sources — `BFF_SOURCE_PAPERS=stub` gives a
stub search with no backend.

## Nothing asked of Django

Everything runs over endpoints that already exist. If corpora outgrow
in-memory ranking, the matcher's rules are the spec for a
`/api/papers/?search=` upgrade (tokenised, ranked); the BFF would then pass
through.
