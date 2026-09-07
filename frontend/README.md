# Research Intelligence

Research Intelligence is an internal research-intelligence tool for an enterprise customer. It
continuously reads new research papers, scores them across the dimensions that
matter (technology readiness, novelty, significance, momentum, rigour, commercial
potential), and surfaces **the next big thing** — starting with the agents & AI
corpus.

It is built for a mixed audience: an executive who wants a two-minute morning
briefing, an analyst who lives in the filters, and a domain expert who wants a
protected hour with one paper. Every score ships with a plain-English rationale
so non-technical users can see _why_ something ranked where it did.

> **Status: Phase 2 core, fully behind the BFF seam.** This branch
> (`phase-2-core`) is the frontend for the Django backend in
> `schwarz-research-intelligence`. Every surface reads real data through
> `src/lib/bff/*` — Ask streams the backend's chat, Briefings derive from
> completed runs (template prose until the backend writes it), Settings save.
> Each `src/app/bff/<resource>/` folder documents the Django endpoint we are
> asking the backend team to build; start at `docs/backend-handoff.md`.
> The concept prototypes and pitch material live on `main`.

## What's here

- **Login** — email or username + password at `/`, exchanged for the backend's
  JWT pair by `/auth/login` and held in httpOnly cookies. There is no self-serve
  sign-up; users and workspace memberships are managed in Django Admin.
- **Domains** — the backend's workspace (criteria, extraction definitions,
  runs) is the analyst's _domain_. Every page spans all the workspaces the
  user belongs to and names the domain per row; there is no switcher and no
  scope cookie (`src/lib/workspace-server.ts`).
- **Core app**:
  - **Home** (`/dashboard`) — the latest completed run in any domain: its
    funnel and the papers it surfaced, sortable by that domain's definitions.
  - **Briefings** (`/briefing`) — one edition per completed run: funnel,
    surfaced papers, the screening log, and a brief (template-written until
    the backend's reporting step lands).
  - **Papers** (`/papers`) — every paper from every domain, scored against its
    domain's extraction definitions plus the backend's composite signal score; domain, screening,
    sort, ingest-window, signal-strength and (when defined) TRL filters; a detail
    page with the score formula, per-dimension rationale and evidence, screening
    notes, and arXiv/DOI links.
  - **Ask** (`/ask`) — corpus- or paper-scoped Q&A streamed from the
    backend's chat engine, with citations, visual evidence, a fact-check
    verdict, and Django-backed history.
  - **Settings** (`/settings`) — profile/password edits and the digest
    toggle, saved to the backend where it can.
- **Bilingual UI** — English source strings with a German dictionary
  (`src/locales/de/`), switched from the user menu.

## Documentation

| Doc                                                        | What's in it                                                                               |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| [`docs/making-it-real.md`](docs/making-it-real.md)         | The roadmap from mock to functional: ingestion, scoring pipeline, embeddings, auth, infra. |
| [`docs/design.md`](docs/design.md)                         | The design system: type, color, charts, layout patterns.                                   |
| [`docs/conventions.md`](docs/conventions.md)               | How we work in a shared checkout: scope, `bun run check`, what never gets committed.       |
| [`docs/tech-preferences.md`](docs/tech-preferences.md)     | The stack we build the real thing on.                                                      |
| [`docs/backend-handoff.md`](docs/backend-handoff.md)       | **For the backend team**: the requested endpoints, conventions, work list, findings.       |
| [`docs/deploy-handoff.md`](docs/deploy-handoff.md)         | Shipping this frontend on Cloud Foundry (subtree, manifest env, smoke checks).             |
| [`src/app/bff/README.md`](src/app/bff/README.md)           | How the BFF seam works: sources/flags, conventions, per-resource contract READMEs.         |
| [`docs/backend-swap-notes.md`](docs/backend-swap-notes.md) | Working notes from wiring this app to the Django backend: topology, API facts, gotchas.    |
| [`docs/backend-swap-plan.md`](docs/backend-swap-plan.md)   | The approved plan for slice 1 (infra + auth + Papers).                                     |

## Project layout

```
src/
  app/
    page.tsx            # / — login (public)
    auth/login, logout  # route handlers: Django JWT ⇄ httpOnly cookies (not under /api)
    bff/                # the seam's HTTP faces + a contract README per resource
    (sidebar)/          # authenticated app
      dashboard/        # Today: latest completed run + the day's brief
      briefing/         # editions from completed runs (+ screening log)
      papers/           # workspace papers + [id] detail
      ask/              # streamed Q&A over the backend chat engine
      settings/         # profile, password, digest preference
  proxy.ts              # reverse-proxies backend prefixes; session gate + token refresh
  lib/
    bff/                # the seam: core/ plumbing + per-resource schema/service/contract
    api/                # server-only Django fetch primitive + inferred DTO types
    auth/               # cookies, JWT decode, session user
    chat/               # useChatStream client hook
    sse/                # SSE parser + writer (shared by server and browser)
    papers/             # pure derivation rules (the backend port reference; bun test)
    workspace-server.ts # the user's domains (all memberships), read by pages
    i18n*.ts            # demo-scale i18n: t() over the German dictionary (chrome only)
  locales/de/           # German dictionary, one module per app area
  fonts/                # self-hosted Switzer + IBM Plex Mono
  components/
    charts.tsx          # inline-SVG chart primitives (dataviz-validated palette)
    scanner-ui.tsx      # shared UI: stat tiles, score rings, badges, cards
    brand.tsx           # Research Intelligence mark + wordmark
contract/               # generated OpenAPI 3.1 (bun run contract:spec)
scripts/                # seed-django.py, contract-spec.ts, contract-check.ts
docs/
```

## Getting started

The frontend needs a running backend. From the `schwarz-research-intelligence`
checkout (SQLite is used when `DB_HOST` is unset):

```bash
cd backend
python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser                                   # your login
python manage.py shell < ../../research-scanner/scripts/seed-django.py   # demo workspace
DEBUG=True python manage.py runserver 8000
```

Then here:

```bash
cp .env.example .env      # BACKEND_INTERNAL_URL=http://localhost:8000
bun install
bun run dev
```

Everything under `/api`, `/admin`, `/static`, `/docs` … is proxied to the
backend by `src/proxy.ts`, so the browser only ever talks to the Next.js
origin — the same shape as production, where Cloud Foundry path-routes one
hostname across the backend apps and this one.

### Tests and checks

```bash
bun run check            # format, types, lint + contract specs, tests, scope
bun run build            # not in `check` — slow; run it after config or routing changes
bun run contract:check   # validates a live Django against the contract
bun run contract:spec    # regenerates contract/*.openapi.json
```

`bun run check` is what to run before committing; see
[`docs/conventions.md`](docs/conventions.md) for the rest of the working
agreements.

### Docker

```bash
docker build \
  --build-arg BUILD_ID=$(git rev-parse HEAD) \
  --build-arg APP_VERSION=$(node scripts/app-version.mjs) \
  -t research-scanner .
docker run -p 3000:3000 -e BACKEND_INTERNAL_URL=http://host.docker.internal:8000 research-scanner
```

### Version

The build shows `v0.1.45` under the sidebar wordmark (commit and build time on
hover) and in `GET /bff/status`. `major.minor` is `package.json`'s version —
bump it by hand when the product moves; the patch is the number of commits
that touched `frontend/`, so every frontend change that reaches `main` deploys
with a new, increasing number and nothing to remember. `node
scripts/app-version.mjs` prints it; `APP_VERSION` overrides it where there is
no git checkout (the Docker image — `deploy.yml` passes it in).

Runtime env: `BACKEND_INTERNAL_URL` (required) and `SITE_URL`, whose scheme
decides whether session cookies carry `Secure`. On Cloud Foundry the
`sri-frontend` app needs those in its `env:` block.

## Real data locally (production snapshot)

Fixtures are hand-written; production extraction output is not (paragraph-long
values, stringified lists, booleans). To design against the real thing without
touching prod or running Django:

```bash
CONTRACT_BASE_URL=https://sri-prod.apps.01.cf.eu01.onstackit.cloud \
CONTRACT_PASSWORD=... bun run snapshot:pull      # → local-data/sri-prod-<date>/
bun run snapshot:serve                           # replays it on :8010
BACKEND_INTERNAL_URL=http://localhost:8010 bun run dev
```

Log in with any username/password. Every GET the BFF makes is answered from
the capture (with `?workspace=` etc. applied); writes return 501, so Ask and
the settings forms are read-only. `local-data/` is git- and docker-ignored —
it is production data. Edit a captured JSON to manufacture the edge case you
want to see.

## Tech

Next.js 16 · React 19 · Tailwind CSS v4 · Bun · Django REST + SimpleJWT (backend).
Design language inspired by Tailwind Plus and Adam
Wathan's 2026-era patterns.
