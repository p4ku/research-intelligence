# 🖥️ Frontend Handover — the new app in `frontend/`

The Next 14 placeholder in `frontend/` has been replaced with the production
frontend developed in the `research-scanner` repo (imported from its
`phase-2-core` branch). **`frontend/` in this repo is now the frontend's
home** — future frontend work happens here.

This document is the bridge for the backend team: what landed, where the
contract documentation lives, and the state of the deploy config outside
`frontend/` (manifest and compose are updated on this branch; two doc
suggestions remain).

---

## 1. What landed

*   **Stack**: Next.js 16 (app router) + Bun + Tailwind v4; multi-stage
    Dockerfile producing a standalone `node server.js` image.
*   **BFF seam**: every piece of data the UI shows flows through
    `frontend/src/app/bff/<resource>/` route handlers backed by services in
    `frontend/src/lib/bff/<resource>/`. Each resource is fed by one of three
    sources — `stub` (fixtures), `composed` (built from today's Django
    endpoints), or `django` (the requested contract endpoint) — switched with
    `BFF_SOURCE_<RESOURCE>` env vars.
*   **Contract-first**: zod schemas are the single source of truth (types,
    runtime validation of Django responses, generated OpenAPI 3.1 in
    `frontend/contract/`). Errors are RFC 9457 `application/problem+json`;
    lists use the DRF page envelope.
*   **Operational view**: `GET /bff/status` (signed in) shows each resource's
    active source and probes which requested Django endpoints exist yet.

---

## 2. Backend team: start here

1.  **`frontend/docs/backend-handoff.md`** — the entry point. Conventions the
    new endpoints must follow, the ordered P1–P3 work list, and prioritised
    backend findings with file:line references.
2.  **`frontend/src/app/bff/<resource>/README.md`** — one per resource
    (papers, workspaces, pipeline-runs, chat, briefings, settings, scoring),
    each with the desired Django endpoint, full JSON examples, curl recipes,
    and done-criteria. `frontend/src/app/bff/README.md` has the working rules.
3.  **`frontend/contract/openapi.json`** — the generated OpenAPI 3.1 spec of
    the Django endpoints being requested (`frontend/contract/bff.openapi.json`
    is the frontend's own face).
4.  **The red/green loop**: with a Django instance running,

    ```bash
    cd frontend && bun install
    CONTRACT_BASE_URL=http://localhost:8000 \
    CONTRACT_USER=admin CONTRACT_PASSWORD=... \
    bun run contract:check
    ```

    Endpoints you haven't built show `MISSING`; build to the contract until
    they `PASS`. Flipping the resource's default to
    `BFF_SOURCE_<RESOURCE>=django` is the "done" signal.

---

## 3. Run the frontend locally

```bash
cd frontend
bun install
cp .env.example .env.local     # point BACKEND_INTERNAL_URL at your Django
bun run dev                    # http://localhost:3000
```

Quality gates: `bun run typecheck && bun run lint && bun test && bun run build`.
`frontend/scripts/seed-django.py` seeds a local Django with a workspace, a
completed pipeline run, and scored papers so every page has data.

---

## 4. Deployment: what already works

`.github/workflows/deploy.yml` needs **no changes**: it builds `./frontend`
with `--build-arg BUILD_ID=<sha>` (the new Dockerfile consumes it and reports
it at `/bff/status`), and the standalone server honours Cloud Foundry's
`$PORT`. The old `frontend/middleware.ts` job of re-proxying `/api`, `/admin`,
`/health` etc. when Gorouter leaks them to the frontend route is taken over by
`frontend/src/proxy.ts` — the manifest's path-scoped routes stay as they are.

---

## 5. Changes outside `frontend/`

The deploy config is updated **on this branch**; two documentation
suggestions remain for the backend team.

### 5.1 `manifest.yml` — done on this branch

`sri-frontend` now has 1G memory and an `env:` block (`NODE_ENV`,
`BACKEND_INTERNAL_URL`, `SITE_URL`, and a commented `BFF_SOURCE_*` table —
uncomment/flip these as contract endpoints land; defaults live in
`frontend/src/lib/bff/core/source.ts`).

Two notes:

*   If `BACKEND_INTERNAL_URL` is ever repointed at a container-to-container
    internal route, that host must be added to Django's `ALLOWED_HOSTS`.
*   The currently *running* app also carries `NEXT_PUBLIC_API_URL` and
    `NEXT_PUBLIC_MCP_URL`, set at some point with `cf set-env` (they are not
    in the manifest). The new app ignores them; they are harmless, but
    `cf unset-env sri-frontend NEXT_PUBLIC_API_URL` (and `..._MCP_URL`)
    tidies them away.

### 5.2 docker-compose `frontend` service — done on this branch

Both `docker-compose.yml` and `docker-compose-develop.yml` now run the
production image (`bun install → next build → node server.js`) with the env
the new app reads, instead of the old npm dev command with `./frontend:/app`
bind mounts. Two operational notes:

*   The container serves a production build — **no hot reload**. For hot
    reload, run `bun run dev` inside `frontend/` on the host.
*   First `docker compose up` after the swap on a machine that ran the old
    app: pass `--renew-anon-volumes` (or `docker compose down -v` first) so
    the old app's anonymous `node_modules`/`.next` volumes don't linger.

### 5.3 `AGENTS.md` — suggested addition

There is no frontend section today. Suggested **Rule 8** under "Rules &
Guidelines for AI Coding Agents":

> ### Rule 8: Frontend Application (`frontend/`)
> The Next.js app in `frontend/` consumes the Django API through its own
> BFF layer and defines the contract for new endpoints. Before building or
> changing an API endpoint the frontend uses, read
> `frontend/docs/backend-handoff.md` and the resource's
> `frontend/src/app/bff/<resource>/README.md`; verify conformance with
> `cd frontend && bun run contract:check`. Never edit `frontend/` to work
> around a backend gap — build the endpoint to the contract instead.

Note: `.agents/AGENTS.md` is a byte-identical copy of `AGENTS.md` — update
both or they drift.

### 5.4 `DEPLOY_STACKIT.md` — stale

It describes the frontend as "Nginx + static React files", names the app
`ri-frontend` (manifest says `sri-frontend`), and shows a manual build against
a different registry host. `deploy.yml` + `manifest.yml` are the truth;
this doc should be corrected or removed.

---

## 6. Smoke checks after a deploy

```bash
curl -si https://<host>/                # 200, login page
curl -si https://<host>/bff/papers     # 401 application/problem+json (no redirect)
curl -si https://<host>/health/        # Django, via the router
# Sign in in a browser: /bff/status lists every resource and its source,
# and a question in Ask streams (watch for `: ping` heartbeat comments).
```

Since 9 Sep 2026 the demo flags are fixed in `frontend/src/lib/features.ts`
(`docs/design/feature-flags.md`): `all_papers` and `ask` off, `stars` on, and
no toggles in the account menu. So `/papers` and `/ask` both render the
not-found card (HTTP 200, streamed inside the shell, since each has a
`loading.tsx`), whatever the `rs-features` cookie says; `/bff/status`
reports the flags under `features`. Delete a flag's `fixed` property to hand
its switch back to the menu.
