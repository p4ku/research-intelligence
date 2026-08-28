# Making it real

Everything in Research Intelligence today runs on the mock corpus in `src/data/` and stubs every
external system. This document is the honest map from prototype to production: what
each capability needs to actually work.

Priorities are labeled **P0** (needed for a functional v1), **P1** (needed to be
genuinely useful), **P2** (differentiators).

## 1. Ingestion pipeline — P0

**Today:** 20 hand-written papers in `src/data/papers.ts`.

**Needed:**

- Source connectors: arXiv (has a clean API + daily feeds), bioRxiv, SSRN, patent
  feeds. Start with arXiv `cs.MA`, `cs.AI`, `cs.CL`, `cs.LG` for the agents corpus.
- A scheduled crawler (cron / queue worker) that pulls new papers, dedupes by DOI /
  arXiv ID, and normalizes metadata (title, authors, abstract, venue, date).
- Full-text fetch where licensing allows (PDF → text), otherwise abstract-only.
- Enrichment: citation counts (Semantic Scholar / OpenAlex API), linked code repos
  and their star counts (GitHub API), author/lab affiliation resolution.
- A `papers` table replacing the mock array. The `Paper` type in
  `src/data/types.ts` is already the target shape; add ingestion metadata
  (source URL, fetched-at, content hash).

## 2. LLM scoring service — P0

**Today:** every `Paper.scores` object and its `rationales` are hand-authored.

**Needed:**

- A scoring worker that, per paper, prompts a model (Claude) to produce each
  insight dimension (0–100, TRL 1–9) **with a one-line rationale**, using a fixed
  rubric per dimension. The rationale is a product feature, not a debug aid — keep
  it.
- TRL is a rubric-based judgment (NASA scale); the prompt should give the model the
  9-level definitions and ask it to justify placement. This is the hardest
  dimension to get consistent — consider few-shot anchoring with human-labeled
  examples.
- Momentum is **not** a single-paper property. Compute it at the trend level from
  citation velocity, follow-up paper count, repo-star deltas, and social signal
  over a rolling window. The paper-level momentum shown today is a proxy.
- Cost control: scores are stable, so score once at ingest and re-score only on
  material change (new citations, a correction). Cache aggressively.
- Calibration: run the scorer over a labeled validation set periodically and track
  drift. Store the rubric version alongside each score so re-scores are auditable.
- Determinism/repeatability: log prompt + model + version with each score so a
  score can be explained and reproduced.

See the Anthropic scoring pattern: batch requests, use structured output
(tool-call schema) so scores validate on the way out, and keep temperature low.

## 3. Trends & clustering — P1

**Today:** 10 hand-written trends; papers reference them by ID.

**Needed:**

- Embed each paper (an embeddings model) and cluster the vector space (HDBSCAN or
  online clustering) to discover topics rather than hand-labeling them.
- Label clusters with a model ("name this cluster of papers").
- Track cluster membership over time to compute stage (emerging / accelerating /
  maturing / cooling) and the momentum spark series.
- Promotion logic: a cluster becomes a "trend" when it crosses size/momentum
  thresholds — this is what the Signal Stream's "trend promoted" event represents.

## 4. Embeddings & the Landscape Map — P2

**Today:** the landscape scatter uses a deterministic pseudo-embedding from scores.

**Needed:** real paper embeddings projected to 2-D (UMAP/t-SNE), recomputed on a
schedule, stored so the map is stable between loads. The time-machine slider needs
per-month snapshots of the projection.

## 5. Tuning that actually steers — P1

**Today:** the Tuning page re-ranks the Top-6 live using `signalScore()` with the
weight sliders — that part is real math on mock data. Sector focus and TRL window
also filter live. Everything else (steering text, precision, cadence, "save
profile") is stubbed.

**Needed:**

- Persist a tuning profile per user (and a team baseline + personal overlay).
- **Plain-English steering** is the killer feature: the free-text guidance should
  be injected into the scoring prompt (or used to bias retrieval), so "favor
  open-source agent frameworks, downweight prompt-engineering papers" actually
  changes what surfaces. This is a scoring-time concern, not a filter.
- The precision dial maps to a confidence threshold on the scorer.
- Feedback loop: thumbs up/down on papers quietly retunes weights (a bandit over
  the weight vector) — see `not-built.md`.

## 6. Persistence & mutations — P0

**Today:** starring a paper, moving a triage card, and toggling settings are
local-only React state.

**Needed:** tables for `user_paper_state` (starred, triage status, notes) and
`tuning_profile`, plus server actions to mutate them. The `Paper.status` and
`Paper.starred` fields model the shape; they just need to move to a join table
keyed by user.

## 7. Auth — mostly real

**Today:** Better Auth is wired with **email/password** only. There is no
self-serve sign-up; accounts are provisioned with `bun run add-user <email>
[password]` (`scripts/add-user.ts`). Route protection is in `src/proxy.ts`.

**Needed to go live:**

- Set `DATABASE_URL` (Neon Postgres) — Better Auth persists sessions/users there.
- For a real enterprise deployment, add SSO/SCIM (Okta/Azure AD) and an allowlist
  or domain restriction so only authorized accounts get in. CLI-provisioned
  email/password accounts are the interim.
- Run the Drizzle migrations (`bun run db:migrate`).

## 8. Notifications & delivery — P1

**Today:** the Settings toggles and the briefing/digest are display-only.

**Needed:** a scheduled job that composes the briefing (§2 model draft), renders it
to email, and sends via a provider; a Slack app for digests and threshold alerts;
webhooks on threshold crossings. The "email-first mode" idea (whole product as a
daily email) is in `ideas.md`.

## 9. MCP server — real shape, mock data

**Today:** `search_papers`, `get_top_signals`, `get_trends` are live tools that
query the mock corpus with real bearer-token auth. Once the corpus is a database,
these work unchanged — they already call the `src/data/` API, which is async by
design precisely so the backing store can swap without touching the tools.

## 10. Infrastructure summary

| Concern                   | Choice implied by the codebase                                             |
| ------------------------- | -------------------------------------------------------------------------- |
| App host                  | Vercel (Next.js 16)                                                        |
| Database                  | Neon Postgres via Drizzle                                                  |
| Auth                      | Better Auth (LinkedIn OIDC)                                                |
| Ingestion/scoring workers | A queue + cron (e.g. Vercel Cron + a worker, or a separate service)        |
| Model calls               | Claude for scoring/rationales/briefing; an embeddings model for clustering |
| Vector store              | pgvector on the same Neon instance, or a dedicated vector DB               |
| Object storage            | PDFs / rendered briefings                                                  |

The web app is the thin, done part. The weight of a real Research Intelligence is the ingestion +
scoring + clustering backend behind the `src/data/` interface.
