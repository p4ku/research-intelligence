# Backend swap — working notes (28 Aug 2026)

Everything learned while cutting `phase-2-core` and wiring it to the Django
backend. Written as a pick-up-cold handover; the decisions here override
older docs where they disagree.

## 1. The two repos

|        | Frontend                                                                                                                                                                                                        | Backend                                                                                     |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Path   | `~/work/research-scanner`                                                                                                                                                                                       | `~/work/schwarz-research-intelligence`                                                      |
| Remote | `Adder-Analytics/research-scanner`                                                                                                                                                                              | `p4ku/schwarz-research-intelligence`                                                        |
| Branch | **`phase-2-core`** is the build-out trunk; `main` is the frozen pitch/demo archive (50 concept pages, Trends/Watchlist, MCP server, pitch docs). All three old `pitch/*` branches are fully merged into `main`. | `main`                                                                                      |
| Stack  | Next.js 16 app router, React 19, Bun, Tailwind v4                                                                                                                                                               | Django REST + SimpleJWT + Celery/Redis + FastMCP, Google GenAI (Vertex, `gemini-3.8-flash`) |

**Hard constraint: the backend cannot be changed. We conform to it exactly as
is.** Gaps are worked around on the frontend or listed in §8 as a handoff.

**Later phase (separate plan):** move server-side data access into Next route
handlers under `/bff/*` (never `/api/*` — see §3) that hit Django. Everything
that talks to Django is already isolated in `src/lib/api/server.ts` +
typed loaders so that move is mechanical; `src/lib/papers/*` (domain types +
mappers) survives it untouched.

## 2. Decisions made with Josh

- Branch name `phase-2-core`, long-lived; `main` untouched.
- In: Today `/dashboard`, Briefings `/briefing`, Papers `/papers` (+ detail with
  paper chat), Ask `/ask`, Settings, login. Out: Trends, Watchlist, all
  concepts, Tuning (dropped in slice 1 — no weights model on the backend), MCP.
- Auth: Django JWT in httpOnly cookies. Better Auth / Neon / Drizzle /
  `add-user.ts` removed.
- UI is **dimension-agnostic**: renders whatever `ExtractionDefinition`s a
  workspace has plus the backend's composite `signal_score`.
- **Workspace** is the top-level scope selector (the backend has no sectors).
- German is **chrome-only**; generated content (abstracts, rationales, chat
  answers, dimension names) is never translated. The ~716 lines of
  data dictionaries (`de/data-papers.ts`, `data-qa.ts`, `data-core.ts`) stay
  only until Ask/Briefings leave the mock corpus.
- Slice order: **1. infra + auth + Papers (done)** → 2. Ask on
  `POST /api/chat/stream/` → 3. Briefings/Today prose → 4. `/bff` migration.

## 3. Deployment topology (why auth had to move)

STACKIT Cloud Foundry, one hostname, path-routed by Gorouter
(`schwarz-research-intelligence/manifest.yml`):

- `sri-api` (Django): `/api /mcp /health /admin /docs /swagger /redoc /schema /static /media`
- `sri-mcp` (FastMCP, `manage.py run_mcp`): `/sse /messages` — for AI clients (API-key auth), **not** a UI event stream
- `sri-worker`, `sri-beat`: Celery, no route
- `sri-frontend`: bare root route, Docker image, **512 MB, no `env:` block**

Consequences:

- **No CORS on Django** (`django-cors-headers` installed, not enabled) → same origin only.
- `/api/auth/*` (Better Auth's path) would be routed to Django → our auth route
  handlers live at **`/auth/login`, `/auth/logout`**. Future route handlers go under `/bff/*`.
- The placeholder frontend's `middleware.ts` reverse-proxied the 12 backend
  prefixes to `BACKEND_INTERNAL_URL` (Gorouter leaks them; locally it is the
  only path to the API). Ported into `src/proxy.ts`.
- CI (`.github/workflows/deploy.yml`) builds `./frontend` with
  `--build-arg BUILD_ID=<sha>`; the simplest integration is `git subtree` of
  `phase-2-core` into `frontend/` so that workflow works unchanged. Not done yet.
- `DEPLOY_STACKIT.md` and `docs/architecture.md` in the backend repo are stale
  (claim Nginx + static export). Trust `manifest.yml` + `deploy.yml` only.

## 4. Backend API facts that shaped the code

- `DefaultRouter`, **trailing slashes mandatory**. Bearer JWT only; access
  60 min, refresh 1 day, **no rotation, no blacklist, no logout endpoint**.
  Login: `POST /api/auth/login/ {username_or_email, password}` →
  `{access, refresh, user:{id, username, email, first_name, last_name, full_name, is_superuser, is_staff}}`;
  errors are `{error: "..."}`. `GET /api/auth/me/` adds `workspaces_count`.
- **No pagination anywhere; no `?workspace=` on `/api/papers/` or
  `/api/extractions/`** — bare arrays across every workspace the user belongs
  to. Only `/api/pipeline-runs/` and `/api/component-runs/` filter
  (`?workspace=`, `?status=`).
- `PaperSerializer` **omits `signal_score`**; it is only on nested
  `metrics[]` (`PaperMetric`, one per `(paper, pipeline_run)`).
- `ExtractionSerializer` is `fields='__all__'` → the model's `exit_metric`
  _property_ is not serialized; `ExtractionDefinitionSerializer` omits the
  configured `exit_metric` key. The frontend therefore derives each
  dimension's value (`src/lib/papers/map.ts` ports `_sanitize_identifier`,
  `_parse_numeric_value` from `tasks/step_6_signal_score/scorer.py` and tiers
  2–3 of `Extraction.exit_metric` in `models.py`).
- `metrics_data` is **pre-filled with `0.0` for every definition** → a
  dimension is `null` only when the paper has no `Extraction` row for it.
- `screening_status` in the wild includes `'accepted'` (absent from model choices).
- `Paper.authors` is a comma-joined `TextField`; no publication date (only
  `created_at`); no tldr/lab/citations/code/stars; no PDF-serving endpoint
  (raw storage keys). We link `Paper.source_url`, which the backend owns
  (arXiv abstract page, DOI, or provider landing page; since 2026-09-07).
- Signal score = `workspace.signal_score_code`, a **user-supplied Python
  snippet** run in a sandbox. There is no weights model (hence no Tuning).
- No sectors, trends, briefings/editions. Nearest analogues: `Workspace`,
  `NarrativeReport` per `PipelineRun` (+ `total_papers_fetched`,
  `total_papers_passed_screening` counters).
- Chat is real: `POST /api/chat/` and `POST /api/chat/stream/` (SSE events
  `metadata, delta, visual_citations, fact_check, usage, done, error`), body
  `{question, paper_id?|workspace_id?, session_id?, deep_thinking?}`.
  It is a **POST**, so `EventSource` won't work — `fetch` + ReadableStream.
  `GET /api/chat/sessions/?paper_id=|workspace_id=` gives history.
- `GET /health/diagnostics/` is unauthenticated and **calls Gemini** — never poll it.
- Zero i18n on the backend; all enum labels/messages arrive in English.
- No seed command/fixtures. `migrate` **auto-creates superuser `admin` /
  `schwarz123!`** (and an MCP API key). `ExtractionDefinition` and
  `signal_score_code` are not REST-writable → seeding goes through
  `manage.py shell` (`scripts/seed-django.py`).
- `python` in Josh's shell is aliased to a missing `python3.12` — call the venv
  binary explicitly (`venv/bin/python manage.py …`).

## 5. What slice 1 shipped (commits on `phase-2-core`)

1. `Cut phase-2-core` — removed concepts, Trends/Watchlist, MCP, pitch docs, screenshots.
2. `Rewire the app for the core-only surface`.
3. `Add Django JWT auth core` — `src/lib/auth/{cookies,jwt,session,safe-next}.ts`,
   `src/lib/api/{backend-url,server}.ts`, `src/app/auth/{login,logout}/route.ts`.
4. `Switch pages and proxy to the Django session` — `src/proxy.ts` (12-prefix
   rewrite → trailing-slash normalisation → public routes → refresh-cookie
   gate → proactive refresh 120 s before `exp`, writing the new `sri_access`
   both as `Set-Cookie` and into the forwarded request so the same render sees it).
5. `Remove Better Auth, Drizzle, Neon, and Vercel couplings` (+ unused
   `ai`/`@ai-sdk`/`streamdown`/`zod`/`dayjs` deps).
6. `Load papers and workspaces from the Django API` — DTOs (`src/lib/api/types.ts`),
   `cache()`d loaders, `ScoredPaper`/`Dimension` domain types, mappers with
   19 `bun test`s, `rs-workspace` cookie + sidebar switcher.
7. `Render papers from the workspace's definitions` — Papers list (screening
   filter defaulting to passed, sort by signal/any definition, ingest window,
   TRL window only if a TRL definition exists), detail page (formula +
   variables, per-dimension rationale/evidence/confidence, screening notes,
   arXiv/DOI links, storage keys as text), dashboard from the latest
   completed run, `ScreeningPill`, null-safe `SignalScore`/`ScoreRow`.
8. `Standalone build, Dockerfile, self-hosted fonts, and a backend seed script`.
9. `Docs`.
10. `Proxy: let Django's trailing-slash URLs through, absolute redirects`.
11. `Login: report backend/config failures as 502, not bad credentials`.
12. `Ignore per-agent build directories` (after a history rewrite that removed
    357 accidentally committed `.next-agent8/` files; force-pushed by Josh).

Cookies: `sri_access`, `sri_refresh`, `sri_user` (display-only, unsigned,
base64url JSON). Flags: httpOnly, SameSite=Lax, Path=/, Secure in production
unless `SITE_URL` is plain http, Max-Age 1 day. Session fields used by chrome:
`name`, `email`, `image?` (never provided by Django), `isStaff`.

Env: `BACKEND_INTERNAL_URL` (required), `SITE_URL`,
`BUILD_ID` (build-time), `BUILD_DIR` (distDir, build-management convention).
`NEXT_PUBLIC_*` is build-time and must not be used for runtime config.

## 6. Gotchas hit during implementation

- Next's default trailing-slash redirect runs **before** the proxy, so every
  `/api/…/` request 308'd instead of being forwarded → `skipTrailingSlashRedirect: true`;
  the proxy normalises the app's own URLs itself.
- The Next proxy rejects relative `Location` headers ("Invalid URL") →
  redirects are built from `x-forwarded-proto` / `x-forwarded-host`.
  Route handlers may return relative `Location` (logout does).
- `next/font` + Turbopack: a dev restart once left a corrupted CSS cache
  (`first-���` parse error). Fix: `rm -rf .next-agent*` and restart.
- `document.cookie = …` inside a component's handler trips the React
  Compiler lint ("This value cannot be modified") → helper in `src/lib/workspace.ts`.
- Route files may only export HTTP methods; helpers like `safeNext` live in `src/lib`.
- `NextResponse` rewrites keep the browser's `Host` header (so Django's
  `ALLOWED_HOSTS` sees `localhost:3008`), but the login route handler's own
  `fetch` uses `BACKEND_INTERNAL_URL`'s host — Django's `ALLOWED_HOSTS` must
  include it (`host.docker.internal` locally in Docker; the C2C internal host
  in CF if that route is used).
- Login handler now maps upstream 401/403 → credentials message, anything
  else → 502 with the status, so a misconfigured host isn't reported as a bad password.
- Pre-existing lint errors (not ours): `papers-browser.tsx` `Date.now` in
  `useMemo`, `dashboard/run-papers.tsx` setState in effect. Pre-existing
  missing DE key: `Any`.

## 7. Verification recipe (what was run, all green)

```bash
# backend (SQLite when DB_HOST is unset; db.sqlite3 is gitignored there)
cd ../schwarz-research-intelligence/backend
python3 -m venv venv && venv/bin/pip install -r requirements.txt
DEBUG=True SECRET_KEY=dev ALLOWED_HOSTS=localhost,127.0.0.1,host.docker.internal \
  venv/bin/python manage.py migrate            # creates admin / schwarz123!
venv/bin/python manage.py shell < ../../research-scanner/scripts/seed-django.py
DEBUG=True SECRET_KEY=dev ALLOWED_HOSTS=localhost,127.0.0.1,host.docker.internal \
  venv/bin/python manage.py runserver 8000

# frontend
BACKEND_INTERNAL_URL=http://localhost:8000 BUILD_DIR=.next-agent8 PORT=3008 bun run dev
bun run typecheck && bunx eslint src && bun test && bun run build
docker build --build-arg BUILD_ID=test -t research-scanner:test .
docker run -p 3009:3000 -e BACKEND_INTERNAL_URL=http://host.docker.internal:8000 -e SITE_URL=http://localhost:3009 research-scanner:test
```

Checked: login by username (email also accepted by Django) → cookies with
the right flags; `/dashboard /papers /papers/<id> /settings /ask /briefing`
200 in EN and DE; unauthenticated → 307 to `/?next=…`; `/health/ /admin/
/docs/ /static/admin/css/base.css /api/auth/me/` proxied; forced-expiry
access token → new `Set-Cookie` and the page renders in the same request;
garbage refresh → cookies cleared + redirect; `next=//evil.com` → `/dashboard`;
cross-site `Origin` → 403; logout → 303 + three `Max-Age=0`; detail page
shows Fit/Novelty/TRL with rationale, evidence, `Confidence 82%`,
`Needs review`, formula, arXiv link; screening filter hides the rejected
paper by default (7 of 10 listed); dashboard reads the run's counters;
container login + pages work.

## 8. Backend wishlist (handoff, not blocking)

Pagination + `?ordering=`; `?workspace=` on papers/extractions/reports/agents;
`signal_score` (+ details) on `PaperSerializer` or a REST
`/api/papers/scorecard/` mirroring the MCP `get_paper_extractions_matrix`;
`exit_metric` on both extraction serializers; PDF/markdown download or
presigned URLs; `ExtractionDefinition` CRUD; member/user endpoints;
`stage_results` / `stop_reason` on the agent serializer; logout/blacklist;
a `BriefingEdition` per run; per-workspace weights if Tuning returns;
CORS if a separate origin is ever needed; `manifest.yml` `sri-frontend`
`env: {BACKEND_INTERNAL_URL, SITE_URL, NODE_ENV}` and likely 1 GB;
`ALLOWED_HOSTS` to include any internal route host.

## 9. Frontend map after slice 1

```
src/proxy.ts                 backend-prefix rewrite, slash normalisation, session gate, refresh
src/app/auth/{login,logout}  route handlers (outside /api)
src/lib/api/server.ts        server-only apiFetch/apiJson (Bearer from cookie, no-store, no retry)
src/lib/api/types.ts         DTOs transcribed from the serializers
src/lib/api/{papers,workspaces,pipeline-runs}.ts   cache()d loaders, in-memory workspace filter
src/lib/papers/{types,map,select}.ts + map.test.ts  domain layer (bun test)
src/lib/auth/*               cookies, jwt decode, session user, safeNext
src/lib/workspace*.ts        rs-workspace cookie; src/components/workspace-switcher.tsx
src/components/scanner-ui.tsx  ScreeningPill, dimensionRadarAxes, null-safe SignalScore/ScoreRow
src/data/                    legacy mock, used by Ask + Briefings only; adapters.ts bridges PaperCard
src/fonts/                   Switzer variable + Plex Mono 400/500/600 (next/font/local)
scripts/seed-django.py       demo workspace for a local backend
```

## 10. Next slices

> **Superseded (28 Aug 2026):** slices 1–3 below shipped as the BFF seam —
> see `docs/backend-handoff.md`, `src/app/bff/README.md`, and the per-resource
> contract READMEs. Deployment: `docs/deploy-handoff.md`. The list is kept
> for history.

1. **Ask** — replace `use-simulated-stream.ts` / `corpus-qa.ts` /
   `ask-history.ts` with `POST /api/chat/stream/` (fetch + ReadableStream,
   parse `event:`/`data:` lines) and `/api/chat/sessions/` for history;
   paper chat on the detail page uses the same with `paper_id`. Then delete
   `src/data/paper-qa.ts`, `de/data-qa.ts`, `de/data-core.ts` dimension labels.
2. **Briefings/Today prose** — decide between deriving from
   `NarrativeReport` + run counters or waiting for a `BriefingEdition`
   model; then delete `src/data/{papers,briefings,pipeline,sectors}.ts`,
   `adapters.ts`, `de/data-papers.ts`, `de/briefing-core.ts` data strings.
3. **`/bff` migration** — separate plan: route handlers under `/bff/*`
   wrapping the `src/lib/api` loaders (`onUnauthorized: 'throw'` → JSON 401),
   pages fetch through them.
4. **Deploy** — subtree `phase-2-core` into the backend repo's `frontend/`
   (or a dedicated workflow pushing `frontend_image`), manifest env block.
