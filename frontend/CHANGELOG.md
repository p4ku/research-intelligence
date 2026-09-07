# Changelog

## 2026-09-07 (stars demo flag)

- Every star affordance is behind the same per-browser demo switch. `stars` off
  and no curation control renders: the corner star on paper cards and archive
  rail rows, the labelled toggle on `/papers/[id]`, `/briefing/[date]` and the
  archive reader, and all four **Starred** filter chips (papers browser,
  briefings ledger, archive rail, edition paper list).
- The ledger loses its whole star **column**, not just the button: `'star'`
  leaves `COLUMNS`, so header cell, body cell, the expanded brief's `colSpan`
  and the skeleton's per-row footprint all follow, and no 28px gutter is left
  behind. Skeletons drop their star bones with them, so nothing flashes.
- Every `starredOnly` derivation is **forced false** rather than merely losing
  its control (`features.stars && state`), in all four lists. A flip taken with
  a Starred filter engaged widens the list back instead of leaving it silently
  narrowed with nothing on screen to clear it. On `/briefing` that state lives
  in the URL, so `?starred=1` survives the flip — a reload with the flag off
  still shows the full ledger.
- Deliberately kept: `GET`/`PUT /bff/stars`, the service, codec, schema and
  contract entries, `stars` in `/bff/status`, every German key, and above all
  the `rs-stars` cookie, which is **not** cleared — flipping the flag back on
  restores the analyst's own stars on the next refresh.

## 2026-09-07 (all_papers demo flag)

- The **Papers** list is behind a per-browser demo switch. `all_papers` off and
  `/papers` no longer exists: a real HTTP 404 on the shared not-found card, the
  nav row filtered out of the rail and the mobile drawer alike, Home's whole
  corpus-search typeahead removed (page and `loading.tsx` together), and the
  404's own "Go to Papers" button gone.
- `/papers/[id]` stays reachable — from briefings, Home's top papers, `/tuning`
  and chat citations — and loses only what is derived from the list: the
  breadcrumb trail, the prev/next pager and its "{n} of {total}", the
  `papers.listAll` fetch that fed them, and the back link, which points at
  Briefings instead. Skeletons make the same call, so nothing flashes.
- Deliberately kept, because the flag is reversible: the German dictionary
  entries, the Playwright journeys that walk `/papers`, `GET /bff/papers`,
  `GET /bff/search` and the papers services. Hiding is a UI concern; the cookie
  is a preference the visitor owns, not an authorization boundary.
- The switch lives in the account menu under **Demo features** (cookie
  `rs-features`; see `src/lib/features.ts`). Flags default ON, so scripted runs
  — screenshots, skeleton drift, Playwright — start cookieless and see the whole
  product.

## 2026-09-01 (Scoring page removed)

- The read-only **Scoring** page (`/scoring`) is gone, along with its nav entry,
  German dictionary and Playwright journey. The URL now 404s. Per-paper score
  explanation stays on `/papers/[id]` (signal ledger + variables).
- The BFF layer behind it is kept on purpose — `GET /bff/scoring`,
  `src/lib/bff/scoring/*` and the `scoring.get.desired` contract entry — so the
  ask on the backend team survives and a future surface can read it.

## 2026-08-31 (build version stamp)

- Every build carries a version, `0.1.<n>`: `major.minor` from `package.json`,
  `n` the number of commits that touched `frontend/` (`scripts/app-version.mjs`,
  inlined by `next.config.mjs`). It sits under the sidebar wordmark with the
  commit and build time on hover, `GET /bff/status` reports `version` and
  `built_at`, and `deploy.yml` also tags the image `v0.1.<n>`.

## 2026-08-28 (backend swap, slice 2: the BFF seam + backend-team handover)

- All data access now flows through a BFF seam: zod contract schemas as the
  single source of truth (`src/lib/bff/<resource>/schema.ts`), services with
  three sources (`stub` fixtures / `composed` from today's endpoints /
  `django` contract pass-through, flipped per resource via `BFF_SOURCE_*`),
  HTTP faces under `/bff/*` with DRF-style pagination and RFC 9457
  problem+json, and `GET /bff/status` probing which requested Django
  endpoints exist yet.
- Ask + paper chat are real: `POST /bff/chat/stream` re-frames Django's chat
  SSE (ids, heartbeats, citations, problem errors); the history rail reads
  Django sessions; corpus scope restored. Briefings derive one edition per
  completed run (funnel, papers, and a real screening log) with template
  prose flagged until the backend writes it. Settings save (profile,
  password, digest toggle). New read-only Scoring page (formula, variables,
  weights, worked example). The mock corpus (`src/data/`) is gone.
- Handover package for the backend team: a README per `src/app/bff/<resource>/`
  folder (UI needs → requested Django endpoint → status → done criteria),
  generated OpenAPI 3.1 (`contract/*.json`, `bun run contract:spec`), a live
  conformance checker (`bun run contract:check`), `docs/backend-handoff.md`
  (ordered work list + prioritised findings), and `docs/deploy-handoff.md`.
- Domain field names went snake_case so the UI's shape IS the contract shape.

## 2026-08-28 (backend swap, slice 1: infra + auth + Papers)

- Auth moved from Better Auth/Neon to the Django backend's JWT: `/auth/login`
  and `/auth/logout` route handlers, httpOnly `sri_*` cookies, refresh in
  `src/proxy.ts`, which also reverse-proxies the backend's URL prefixes.
- Papers, paper detail, and the dashboard read the Django API through a
  server-only client (`src/lib/api`) and a dimension-agnostic domain layer
  (`src/lib/papers`): whatever extraction definitions a workspace has, plus
  the backend's composite signal score. Workspace switcher in the sidebar.
- Tuning removed; Trends/Watchlist already gone. Ask and Briefings stay on
  the mock corpus until their slices.
- Standalone build + Dockerfile for Cloud Foundry; fonts self-hosted; Vercel
  and Drizzle dependencies removed. `scripts/seed-django.py` seeds a local
  backend for development.

## 2026-08-27 (phase-2-core cut)

- Branched `phase-2-core` from `main` as the build-out trunk. It keeps only
  the core product: Today, Briefings, Papers (+ deep dive), Ask, Tuning,
  Settings, login and Better Auth.
- Removed from this branch (still on `main`): Trends and Watchlist, all fifty
  `/concepts/*` prototypes and their registry, the Phase 3a/3b/Tier sidebar
  sections and hide/preview toggles, the MCP server, concept-only mock data
  (trends, authors, lineage, digest, hand-off, signals), the concept German
  dictionaries, the `docs/` pitch and report material, and the screenshot
  tooling.
- Mock corpus and the simulated Ask / paper Q&A stay as the baseline to build
  against.

## 2026-07-07 (second reading)

- Added three **second-reading concepts** — Second Round, Mandates, and
  Engagements — from re-reading the raw 1 July workshop notes against the
  pool (four ideation lenses, eight candidates, three adversarial judges,
  three winners; see `docs/brainstorm/evaluation-second-reading.md`).
- Second Round closes the loop the Docket's "Accept — second-round
  evaluation" button pointed at: the workshop's four deep checks scored by
  named desks, with computed machine-vs-desk divergence flags.
- Mandates renders the two-track directive: the ten defined topics as a duty
  roster with per-topic cadence dials negotiated against a live review-load
  bar; Track 2 stays a dashed wildcard lane.
- Engagements tracks author relationships past send, with an amber
  "field is outpacing this conversation" flag derived from attention curves
  vs. touch cadence, and misses shelved at equal weight.

## 2026-07-03 (blindspot round)

- Added five blindspot-round concept pages — The Editing Desk, The Near-Miss
  Shelf, Expert Hour, Receipts, and Ripple — from a pass that read the signed
  Schwarz proposal against the concept pool (eight candidates, three adversarial
  judges, five winners; see `docs/brainstorm/evaluation-blindspots.md`).

## 2026-07-03 (gap-analysis wave)

- Added four **gap-analysis concepts** — Dry Run, The Miss Ledger, The
  Sign-Off, and Positions — from diffing the May 2026 proposal against the
  built set (see `docs/brainstorm/gap-analysis-jul2026.md`).

## 2026-07-03 (workshop wave)

- Added seven **workshop-wave concepts** from the 1 July Schwarz Digits session:
  Hand-off Packets, Weekly Momentum, AgentSLR Pipeline, Pushed Digest, Paper
  Lineage, Author Intelligence, and Paper Dig-In.
- Extended the mock data layer with authors (bibliometrics + reach-out drafts),
  paper lineages, a pipeline run with an exclusion log, hand-off packets with
  weekly throughput stats, and a pushed digest.
- Added the **workshop signals** strip (breakout probability, TRL, author
  strength, citation velocity) to the paper detail page, packets, and lineage.
- Relabeled the Commercial dimension to **Schwarz fit** — a configurable lens
  with reduced default weight, ordered last in scoring UIs.
- Paper detail gained a "Go deeper" section (lineage / author / dig-in /
  packet); the dashboard links to Weekly Momentum; the concepts index and
  sidebar group the workshop wave.

## 2026-07-03

- Initial release of **Research Scanner**, a research-intelligence tool for an
  internal enterprise customer, with a clean login page.
- Added a typed mock corpus (papers, trends, sectors, LLM scores) and a
  Signal-Score engine with a live-tuning preview.
- Built core pages: Dashboard, Papers (+deep dive), Trends (+detail), Watchlist,
  Tuning, Settings.
- Added a **Concepts** section with ten divergent interface prototypes.
- Added MCP tools: `search_papers`, `get_top_signals`, `get_trends`.
- Documented the ideation, concepts, design system, what's not built, and the
  path to a functional product under `docs/`.
