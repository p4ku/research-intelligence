# Swap `phase-2-core` in as the frontend for `schwarz-research-intelligence` — slice 1: infra + auth + Papers

## Context

`~/work/schwarz-research-intelligence` (github `p4ku/…`) is the real backend: Django REST (SimpleJWT) + Celery + FastMCP, deployed to STACKIT Cloud Foundry as five apps sharing one hostname, path-routed (`sri-api` owns `/api /admin /static /media /health /docs /swagger /redoc /schema /mcp`; `sri-mcp` owns `/sse /messages`; `sri-frontend` gets the bare root). Its `frontend/` is a Next 14 placeholder we are replacing with `research-scanner@phase-2-core`.

**Hard constraint: the backend cannot be changed. We conform to it exactly as is.** Gaps become a wishlist (§H), not dependencies.

**Later, separate plan:** migrate server-side data access into Next route handlers (under `/bff/*`, never `/api/*`) that hit Django. Everything that talks to Django is therefore isolated in `src/lib/api/server.ts` + typed loaders so that move is mechanical; the domain layer (`src/lib/papers/*`) survives it untouched.

### Decisions (28 Aug 2026)

- Auth: Django JWT in httpOnly cookies; Better Auth / Neon / Drizzle / `add-user.ts` removed.
- UI is dimension-agnostic: render whatever `ExtractionDefinition`s the workspace has + backend `signal_score`. Tuning dropped from core nav.
- Workspace is the top-level scope selector (no sectors on the backend).
- German is chrome-only; data dictionaries go.
- Slice 1 = infra + auth + Papers (+ dashboard paper list). Ask, Briefings/Today prose, Settings follow in later slices and stay on mock for now.

### Gotchas that shaped this (full review in git history of this file; key ones)

- `/api/auth/*` collision: Better Auth's handler path is routed to Django by Gorouter → auth must move outside `/api`.
- No CORS on Django (package present, not enabled) → same-origin only; the placeholder's `middleware.ts` reverse-proxies the 12 backend prefixes to `BACKEND_INTERNAL_URL` and is the only path to the API locally → must be ported into `src/proxy.ts`.
- No pagination, no `?workspace=` on `/api/papers/` or `/api/extractions/` → bare arrays of everything across the user's workspaces; compose in memory.
- `PaperSerializer` omits `signal_score` → read nested `metrics[]` (`PaperMetric`, per `(paper, pipeline_run)`). `ExtractionSerializer` is `fields='__all__'` so the `exit_metric` _property_ is not serialized; `ExtractionDefinitionSerializer` omits `exit_metric` → the frontend must derive dimension values (port of `scorer._sanitize_identifier` / `_parse_numeric_value` and tiers 2–3 of `Extraction.exit_metric`).
- `Paper.authors` is a comma-joined `TextField`; no published date (only `created_at`); no tldr/lab/citations/code fields; no PDF-serving endpoint (raw storage keys) — use `https://arxiv.org/pdf/{arxiv_id}.pdf` / `https://doi.org/{doi}` like the MCP matrix tool does.
- `metrics_data` pre-fills every definition with `0.0` → a dimension is `null` only when the paper has no `Extraction` row for it.
- `screening_status` in the wild includes `'accepted'` (not in model choices).
- Refresh tokens don't rotate and there's no logout/blacklist → parallel refreshes are harmless; logout is cookie-clearing only.
- `NEXT_PUBLIC_*` is build-time; runtime config must be plain env (`BACKEND_INTERNAL_URL`, `SITE_URL`).
- Next 16: `cookies()` async; `proxy.ts` runs on Node; `response.cookies.set` defaults `path` to the request path → always pass `path: '/'`.
- No seed command/fixtures in the backend; `ExtractionDefinition` and `signal_score_code` aren't REST-writable → seed via `manage.py shell` script kept in _our_ repo.

## A. Auth core (commit 1: "Add Django JWT auth core")

New files:

- `src/lib/auth/cookies.ts` (pure, no `next/headers`): `ACCESS_COOKIE='sri_access'`, `REFRESH_COOKIE='sri_refresh'`, `USER_COOKIE='sri_user'` (base64url JSON `{id, username, email, name, isStaff}` from login's `user`, `name = full_name`); `authCookieOptions()` → `{httpOnly:true, sameSite:'lax', path:'/', secure: NODE_ENV==='production' && !SITE_URL.startsWith('http://'), maxAge: 86400}`; `clearAuthCookies(store)` works on both `ResponseCookies` and the `cookies()` store.
- `src/lib/auth/jwt.ts` (pure): `decodeJwtPayload`, `secondsUntilExpiry` via `Buffer.from(b64url,'base64url')`. No verification — Django verifies.
- `src/lib/auth/session.ts` (`server-only`): `SessionUser {id, username, name, email, image?, isStaff}`; `getSessionUser()` reads `sri_user` (falls back to one `GET /api/auth/me/` if `sri_access` exists without `sri_user`); `hasSessionCookies()`.
- `src/lib/api/backend-url.ts` (pure): `backendUrl()` = `BACKEND_INTERNAL_URL` → `NEXT_PUBLIC_API_URL` minus `/api` → `http://localhost:8000`, trailing slash stripped.
- `src/lib/api/server.ts` (`server-only`): `class ApiError(status, body)`; `apiFetch(path, init)` adds `Authorization: Bearer <sri_access>`, `Accept: application/json`, `cache:'no-store'`, never retries; `apiJson<T>(path, init & {onUnauthorized?: 'redirect'|'throw'})` — default redirects to `/auth/logout?reason=expired`, `'throw'` raises `ApiError` (what the later `/bff` handlers will use).
- `src/app/auth/login/route.ts` — `POST {identifier, password, next?}` → `POST ${backend}/api/auth/login/ {username_or_email, password}`; on 200 set the three cookies, respond `{ok, redirect}` (sanitised `next`: must start with `/` and not `//`, default `/dashboard`); pass Django 401/403 through. Check `Sec-Fetch-Site`/`Origin` is same-origin.
- `src/app/auth/logout/route.ts` — `POST` and `GET` clear cookies, `303` → `/`.
- `.env.example` (`BACKEND_INTERNAL_URL=http://localhost:8000`, `SITE_URL`) + `!.env.example` in `.gitignore`. Add `server-only` dep.

## B. Pages + proxy on the Django session (commit 2)

- `src/proxy.ts` rewrite: (1) if path matches `^/(admin|api|mcp|docs|swagger|redoc|schema|static|media|health|sse|messages)(/|$)` → `NextResponse.rewrite(new URL(pathname+search, backendUrl()))`; (2) public: `/`, `/auth/*`, `/opengraph-image`, `/twitter-image`, `/robots.txt` → next; (3) no `sri_refresh` → redirect `/?next=<path>`; (4) access valid for > 120 s → next; (5) else `POST /api/auth/refresh/ {refresh}` → set new `sri_access` (path `/`) on the response, or clear all cookies and redirect to `/`. Matcher: existing static-excluding pattern **plus** `'/(admin|api|…|messages)/:path*'` and the bare-prefix form so `/static/admin/css/base.css` is caught. **Dev bypass removed.**
- `src/app/page.tsx`: `if (await hasSessionCookies()) redirect('/dashboard')`; pass `searchParams.next` to `<LoginPanel next>`.
- `src/app/login-panel.tsx`: `fetch('/auth/login', …)` then `window.location.assign(redirect)`; drop the `includes('@')` branching (Django handles both).
- `src/app/(sidebar)/layout.tsx`: `const user = await getSessionUser(); if (!user) redirect('/')`; load `workspaces` + current workspace (§D) and pass `user`, `workspaces`, `currentWorkspaceId` into `ApplicationLayout`.
- `src/app/(sidebar)/application-layout.tsx`: props replace `authClient.useSession`; `handleSignOut` → `fetch('/auth/logout',{method:'POST'})` then `window.location.assign('/')`; remove `/tuning` from `coreNav`; add `WorkspaceSwitcher` section under the header.
- `dashboard/page.tsx` greeting and `settings/page.tsx` profile via `getSessionUser()`; settings additionally `apiJson('/api/auth/me/')` for role (`is_superuser`/`is_staff`), falling back to the cookie user on `ApiError`.

## C. Remove Better Auth, Drizzle, Neon, Vercel (commit 3)

Delete: `src/lib/auth.ts`, `src/lib/auth-client.ts`, `src/lib/db/`, `src/app/api/` (entire — `/api` is Django's), `scripts/add-user.ts` (and `scripts/`), `drizzle/`, `drizzle.config.ts`, `.vercel/`, `.env.local`; `.env` → `BACKEND_INTERNAL_URL` only. In `src/app/layout.tsx` drop `@vercel/analytics` and read `SITE_URL` (runtime) instead of `NEXT_PUBLIC_SITE_URL`. Drop `runtime='edge'` from `opengraph-image.tsx`/`twitter-image.tsx`.
`package.json`: remove `better-auth, drizzle-orm, drizzle-kit, @neondatabase/serverless, @vercel/analytics, ai, @ai-sdk/google, @ai-sdk/react, streamdown, @streamdown/*`, and (zero importers) `use-stick-to-bottom, react-use-measure, zod, dayjs`; remove scripts `db:*`, `add-user`, `build:separate`. Update `README.md`, `docs/tech-preferences.md` (Auth/Database/Analytics rows), `CHANGELOG.md`.

## D. Workspace scope + Papers data layer (commit 4: "Load papers from the Django API")

- `src/lib/api/types.ts` — DTOs transcribed from the serializers: `PaperDTO` (`authors: string`, `metrics: PaperMetricDTO[]`, `screening_status` incl. `'accepted'`), `PaperMetricDTO` (`signal_score: number|null`, `signal_score_details {variables, code_snippet, score, calculated_at, error}`, `metrics_data`), `ExtractionDTO` (`fields_data` flat **or** `{fields:{…}}` nested with `{value, normalized_value?, confidence?, evidence?:[{quote, rationale}]}`; `extraction_definition: string|null`; `category`; `validation_status`; `confidence_score`), `ExtractionDefinitionDTO` (no `exit_metric`), `WorkspaceDTO` (`extraction_definitions[]`, `user_role`; Decimals arrive as strings), `PipelineRunDTO`.
- `src/lib/api/workspaces.ts` — `listWorkspaces = cache(() => apiJson('/api/workspaces/'))`.
- `src/lib/api/papers.ts` — `cache()`d raw loaders `listPapersRaw`, `listExtractionsRaw`, `getPaperRaw(id)`; `listScoredPapers(workspaceId)` = `Promise.all` of the three, filter papers by workspace, group extractions by `paper`, map with the workspace's definitions; `getScoredPaper(id)` (404 → null). Comment: this is the one place that becomes pagination-aware if the backend ever adds it.
- `src/lib/api/pipeline-runs.ts` — `listRuns(workspaceId, status?)` via the supported `?workspace=&status=`.
- `src/lib/papers/types.ts` — `ScoredPaper` (`id, workspaceId, pipelineRunId, title, authors[], authorsRaw, abstract, doi, arxivId, source, screeningStatus, screeningReasoning, signalScore|null, signalScoreDetails|null, dimensions[], pdfKey, markdownKey, pdfUrl, isBenchmark, evaluationLabel, createdAt`), `Dimension` (`key, definitionId, name, value|null, raw, max|null, isTrl, rationale?, evidence?, confidence?, validationStatus?, reviewRequired?`), `WorkspaceSummary`, `PASSED_STATUSES`. Mock `Paper` type stays for Ask/Briefings this slice.
- `src/lib/papers/map.ts` (pure; `bun test`): `sanitizeIdentifier` (port of `scorer._sanitize_identifier`), `parseNumeric` (port of `_parse_numeric_value` returning `null` not `0`), `resolveExitMetric` (tiers 2–3 of `Extraction.exit_metric`, unwrap `.fields`, key compare lowercased/space→underscore), `resolveDimension` (no extraction → null; `metrics_data[key]` number preferred; TRL by `/\btrl\b/i` clamped 1–9 max 9; rationale/evidence from nested `evidence[]` or sibling keys `/(reason|rationale|justif)/i` and `/(evidence|quote)/i`; `max` via `inferScale` — TRL 9, a `(\d+)\s*(-|–|to)\s*(\d+)` range in name/system_prompt, else corpus max ≤10→10, ≤100→100, else null), `pickMetric` (match `pipeline_run`, else newest), `splitAuthors`, `pdfUrl`. Legacy `metrics_data.trl_score` → synthesized TRL dimension.
- `src/lib/workspace.ts` (`WORKSPACE_COOKIE='rs-workspace'`) + `src/lib/workspace-server.ts` `getCurrentWorkspace()` (cookie → validated against `listWorkspaces()` → first workspace → null). `src/components/workspace-switcher.tsx` (client) mirrors the language toggle: write cookie, `router.refresh()`.
- Tests: `src/lib/papers/map.test.ts` — parity cases (`'TRL Level'→'trl_level'`, `'Fit-Score (0-100)'→'fit_score_0_100'`, `"TRL 4"→4`, `"85%"→0.85`, `"High"→null`, flat vs nested `fields_data`, `0.0` in `metrics_data` with no extraction → null).

## E. Papers + dashboard pages (commit 5: "Render papers from the workspace's definitions")

- `papers/page.tsx`: `getCurrentWorkspace()` → `NoWorkspaceState` or `listScoredPapers`; `force-dynamic`; `papers/error.tsx` boundary with retry.
- `papers/papers-browser.tsx`: drop sector filter/`lab`; add **Screening** filter (default = passed statuses; Borderline/Pending/Rejected/Withdrawn/All); sort = `signal` (nulls last), `recent` (`createdAt`), plus one `dim:<key>` per numeric definition; "Published" → "Ingested" on `createdAt`; signal slider max = `max(100, ceil(maxObserved))`; TRL window only when a TRL definition exists; search over title/abstract/authors/arxivId/doi; keep client-side `PER_PAGE` pagination.
- `papers/[id]/page.tsx`: delete `generateStaticParams`; `getScoredPaper` (deduped with `generateMetadata`); header = `ScreeningPill · source · formatDate(createdAt)`, arXiv/DOI links; **Signal score** card (`SignalScore` clamped, raw number, variables `dl`, `code_snippet` in `<details>`, formula-error tag); **Dimensions** card via extended `ScoreRow` (null-safe `value/max`, `raw`, `evidence[]`, confidence/validation tags); radar only when ≥3 numeric dims (`dimensionRadarAxes`); **Screening** card with reasoning; abstract; **Files** row (external link or mono storage key + "no file endpoint yet"). `TrlBadge` only with a TRL dim.
- `components/paper-card.tsx`: `paper: ScoredPaper`; `SignalScore` accepts `null`; `SectorChip` → new `ScreeningPill` in `scanner-ui.tsx`; abstract `line-clamp-2` instead of `t(tldr)`; stats = TRL badge + first two non-TRL numeric dims; first author + "et al." instead of `lab`; no star.
- Delete `papers/[id]/paper-actions.tsx` (already unused). `paper-chat.tsx`: stays simulated, `composeQAs(paper)` from real fields; file comment naming `POST /api/chat/stream/` for the Ask slice.
- `src/data/adapters.ts` `mockPaperToScored()` so `briefing/[date]/page.tsx` keeps compiling against the new `PaperCard` (deleted in the Briefings slice).
- `dashboard/page.tsx`: latest completed run via `listRuns(ws.id,'completed')[0]`; papers = scored papers with `pipelineRunId === latest.id` and passed status; funnel from `total_papers_fetched` / `total_papers_passed_screening` / `papers.length`; eyebrow = `formatDate(completed_at ?? run_date)`; workspace name replaces sector chips; empty state "No completed runs yet"; keep `todayInBrief` mock prose with a comment. `run-papers.tsx` tabs = Overall + one per numeric definition.
- Delete `src/app/(sidebar)/tuning/`, `de/tuning.ts` (+ spread), `'nav|Tuning'`. `src/data/index.ts`: remove `PaperQuery/getPapers/getRunPapers`; header comment "legacy mock for Ask/Briefings only". Keep `papers.ts`, `paper-qa.ts`, `sectors.ts`, `briefings.ts`, `pipeline.ts`, `types.ts` this slice.
- i18n: remove `t()` around data in `paper-card`, `papers/[id]`, `paper-chat`, `run-papers` (dimension names verbatim); trim `de/papers.ts` (sector/star/tldr/why/trends keys) and add the new chrome keys (Screening, Passed, Borderline, Pending, Rejected, Withdrawn, All statuses, Ingested, Unscored, Formula, Variables, Evidence, Confidence, Needs review, Stored PDF, Open on arXiv, Open DOI, No file endpoint yet, No papers in {workspace} yet, No workspace selected, Backend session expired, Retry); `de/chrome.ts` add Workspace/Switch workspace; `de/dashboard.ts` drop the hardcoded date, add "No completed runs yet". `de/data-papers.ts`/`data-qa.ts`/`data-core.ts` stay until the Ask slice (mark headers "delete with src/data/papers.ts").

## F. Standalone build + Dockerfile (commit 6) and fonts (commit 7)

- `next.config.mjs`: `output:'standalone'`, `generateBuildId: async () => process.env.BUILD_ID ?? null`, `distDir: process.env.BUILD_DIR || '.next'` (what the build-management skill expects), keep `turbopack.root` and headers.
- `Dockerfile` (repo root): `node:22-alpine` base with the `bun` binary copied from `oven/bun:1-alpine`; `bun install --frozen-lockfile`; `ARG BUILD_ID`; `bun run build`; runtime stage copies `.next/standalone`, `.next/static`, `public`; `USER node`; `CMD ["node","server.js"]`; honours CF-injected `PORT`. `.dockerignore`: `node_modules .next* .git .vercel .env* docs *.md .claude`.
- Fonts: vendor Switzer variable + IBM Plex Mono 400/500/600 woff2 into `src/fonts/`, `next/font/local` in `layout.tsx` with `--font-switzer`/`--font-plex-mono`, update `--font-sans`/`--font-mono` in `src/styles/tailwind.css`, remove the three CDN `<link>`s (GDPR + corporate egress).

## G. Seeding (for verification; lives in our repo)

`scripts/seed-django.py`, run as `python manage.py shell < ../research-scanner/scripts/seed-django.py` against a local SQLite Django (`DB_HOST` unset): idempotent by workspace name; creates workspace with `signal_score_code`, `WorkspaceMember` for the dev user, definitions "Fit Score" / "Novelty Score" / "TRL Level", a completed `PipelineRun`, ~10 papers (mixed statuses incl. one rejected and one unscored; flat and nested `fields_data`; one non-numeric "High"), then `compute_paper_signal_score()` for the passed ones. Modelled on `research_intelligence/tests/test_signal_score_e2e.py`.

## H. Backend wishlist (handoff, not blocking)

Pagination + `?ordering=`; `?workspace=` on papers/extractions/reports/agents; `signal_score` in `PaperSerializer` or a REST `/api/papers/scorecard/` mirroring `get_paper_extractions_matrix`; `exit_metric` on `ExtractionDefinitionSerializer` and `ExtractionSerializer`; PDF/markdown download endpoint; `ExtractionDefinition` CRUD; member/user endpoints; `stage_results`/`stop_reason` on the agent serializer; logout/blacklist; `BriefingEdition` per run; `manifest.yml` `sri-frontend` `env: {BACKEND_INTERNAL_URL, SITE_URL, NODE_ENV}` (+ likely 1G memory); frontend image source: `git subtree` of `phase-2-core` into `frontend/` so `deploy.yml` (`context: ./frontend`, `--build-arg BUILD_ID`) works unchanged.

## Verification

1. `bun install && bun run typecheck && bun run lint && bun test && bun run build` (via build-management dir); `.next*/standalone/server.js` exists.
2. Backend local: `cd ../schwarz-research-intelligence/backend && python -m venv venv && pip install -r requirements.txt && python manage.py migrate && createsuperuser && runserver 8000`; run the seed script.
3. `BACKEND_INTERNAL_URL=http://localhost:8000 bun run dev` (port per build-management): login by email and by username → `/dashboard`; DevTools cookies `sri_access/sri_refresh/sri_user` HttpOnly, Lax, Path=/; `/?next=/settings` lands on settings, `/?next=//evil.com` lands on dashboard.
4. Refresh: set `sri_access` to an expired JWT → navigation returns a new `Set-Cookie` and the page renders (proves same-request visibility); delete `sri_refresh` → redirect to `/`; garbage `sri_refresh` → cookies cleared. Restart Django with a new `SECRET_KEY` → `/settings` → `/auth/logout?reason=expired` → `/`.
5. Proxy: `localhost:3000/admin/` renders with CSS, `/docs/` shows Swagger, `/api/auth/me/` unauthenticated → Django 401 JSON. Logout from the sidebar clears cookies; `curl -X POST /auth/logout -i` → 303 + three `Max-Age=0` cookies.
6. Papers: list sorted with unscored last; Screening default hides the rejected paper; TRL filter present only for the seeded workspace; sort options = definition names; detail shows rationale/evidence for the nested fixture and the raw "High" chip; arXiv link when `arxiv_id` set; dashboard funnel equals run counters; switching workspace re-renders every page; German toggle changes chrome only.
7. `docker build --build-arg BUILD_ID=test -t research-scanner . && docker run -p 3000:3000 -e BACKEND_INTERNAL_URL=http://host.docker.internal:8000 research-scanner` → `/` 200, `/health` returns Django JSON.
8. `git diff --stat main..phase-2-core` sanity; commit sequence A→G as listed.
