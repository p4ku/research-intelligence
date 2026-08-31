# The BFF seam (`/bff/*`)

Every piece of data the UI shows flows through one seam per resource:

```
page/component ──(import)──▶ src/lib/bff/<resource>/service.ts ──▶ Django
client component ──(fetch /bff/<resource>)──▶ src/app/bff/<resource>/route.ts ─┘
```

- **Server components** import the service directly (no loopback HTTP).
- **Client components** fetch the HTTP face with `bffFetch` (`src/lib/bff/client.ts`).
- The routes live under `/bff` because Cloud Foundry path-routes `/api/*`
  straight to Django — our own HTTP routes must never live there. BFF URLs
  have **no trailing slash** (Django's have a mandatory one).

Each resource folder here carries a `README.md` with the same section order:
purpose → what the UI needs → BFF routes → **the Django endpoint we are asking
the backend team to build** → how it works today → how to flip the flag →
curl examples → done criteria. Start at
[`docs/backend-handoff.md`](../../../docs/backend-handoff.md) for the ordered
work list.

## Sources and flags

Every resource is fed by one of three sources (`src/lib/bff/core/source.ts`):

| Source     | Meaning                                                              |
| ---------- | -------------------------------------------------------------------- |
| `stub`     | Checked-in fixtures in the contract shape. No backend needed.        |
| `composed` | Assembled in the BFF from the Django endpoints that exist today.     |
| `django`   | The requested contract endpoint, as a validated pass-through.        |

Flip with `BFF_SOURCE_<RESOURCE>=stub|composed|django` (see `.env.example`).
Every BFF response carries `X-BFF-Source`. `GET /bff/status` (signed in)
shows the active source per resource and probes whether each requested Django
endpoint exists yet. **Flipping a resource's default to `django` is the "done"
signal for its contract.**

## Conventions (ours, and what we ask of new Django endpoints)

- Lists: DRF page-number envelope `{count, next, previous, results}` with
  `?page=&page_size=&ordering=&search=`. `page_size` ≤ 200.
- Errors: RFC 9457 `application/problem+json` —
  `{type: "/problems/<slug>", title, status, detail?, instance?, errors?}`,
  `errors` being DRF-style field errors. Slug table in `docs/backend-handoff.md`.
- Timestamps ISO 8601 UTC; ids UUID; JSON keys `snake_case`.
- Chat streaming: SSE frames `id: <n>` / `event: <name>` / `data: <one-line JSON>`
  with `: ping` comments every 15 s (contract in `chat/README.md`).
- Contracts are zod schemas (`src/lib/bff/<resource>/schema.ts`) — the single
  source of truth. OpenAPI 3.1 is generated from them into `contract/`.

## Working on this locally

```bash
# Backend (SQLite; migrate auto-creates admin / schwarz123!):
cd ../schwarz-research-intelligence/backend && venv/bin/python manage.py runserver 8000
# Seed once: venv/bin/python manage.py shell < ../../research-scanner/scripts/seed-django.py

# Frontend:
BACKEND_INTERNAL_URL=http://localhost:8000 bun run dev

# Checks:
bun run typecheck && bun run lint && bun test && bun run build
bun run contract:check     # validates a live Django against the contract
bun run contract:spec      # regenerates contract/*.openapi.json
```

## Done criteria for a resource (template)

1. The Django endpoint(s) in this folder's README exist and
   `bun run contract:check` reports **PASS** for them.
2. A real response was captured and the folder's fixtures refreshed from it.
3. The resource's default source is flipped to `django`
   (`src/lib/bff/core/source.ts`) and `/bff/status` shows `present`.
4. The env table in `docs/deploy-handoff.md` is updated.

`/auth/login` and `/auth/logout` are not BFF resources — they are the cookie
bridge to Django's existing `POST /api/auth/login/` / `POST /api/auth/refresh/`.
