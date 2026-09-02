# Backend handoff — what the frontend needs from Django

_For the backend team and its coding agents. Written 28 Aug 2026 from
`research-scanner@phase-2-core`; the authoritative, machine-readable contract
is generated into [`contract/openapi.json`](../contract/openapi.json) and
each endpoint has a folder README under [`src/app/bff/`](../src/app/bff/)._

## How to work on this

The frontend routes all data access through a **BFF seam**: one folder per
resource under `src/app/bff/<resource>/`, each carrying a README with the
same section order — what the UI needs, the BFF routes, **the Django
endpoint(s) we are asking for** (with JSON examples), how it works today, how
to flip the flag, curl examples, and done criteria. Every resource is fed by
`stub` (fixtures), `composed` (assembled from today's endpoints), or `django`
(your endpoint, validated); `GET /bff/status` shows the live picture and
probes whether each requested endpoint exists.

Your red/green loop:

```bash
# in research-scanner/  (backend running with a seeded workspace)
bun install
CONTRACT_BASE_URL=http://localhost:8000 CONTRACT_USER=admin CONTRACT_PASSWORD=… \
  bun run contract:check
```

The checker logs in, discovers sample ids, executes every GET in the
contract, and prints `PASS / MISSING / MISMATCH` (with the offending key
paths). **Current** endpoints must stay PASS — they are what the app runs on
today. **Requested** endpoints start MISSING; build until PASS, then flip the
resource's default in `src/lib/bff/core/source.ts` (that is the done signal).

## Conventions requested for new endpoints

- **Lists**: DRF page-number pagination `{count, next, previous, results}`,
  params `?page=&page_size=&ordering=&search=`.
- **Errors**: RFC 9457 `application/problem+json` via a DRF
  `EXCEPTION_HANDLER`: `{type: "/problems/<slug>", title, status, detail?,
errors?: {field: [msg]}}`. Slugs: `validation` 400, `unauthenticated` 401,
  `forbidden` 403, `not-found` 404, `method-not-allowed` 405, `conflict` 409,
  `internal` 500.
- ISO 8601 UTC timestamps, UUID ids, `snake_case` keys, trailing slashes as
  usual.
- **OpenAPI 3.1**: drf-spectacular is installed — set
  `SPECTACULAR_SETTINGS["OAS_VERSION"] = "3.1.0"` and annotate the new views
  so your schema can be diffed against `contract/openapi.json`.
- SSE (chat): frames `id: <n>\nevent: <name>\ndata: <one-line JSON>\n\n`,
  `: ping` comments every ≤15 s.

## Ordered work list

| P      | Work                                                                                                                                                                                                                                                                                                                                                                                                         | Contract                                                                                                        | Size |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- | ---- |
| **P1** | Workspace-scoped, paginated papers **scorecard** (`GET /api/workspaces/{id}/papers/`, `GET /api/papers/{id}/scorecard/`) — papers with `signal_score` + resolved dimensions inline. Port reference: `src/lib/papers/map.ts` (+ `map.test.ts` as acceptance cases), composition `src/lib/bff/papers/compose.ts`. Removes the O(corpus) in-memory join on every page view.                                     | [`src/app/bff/papers/`](../src/app/bff/papers/README.md)                                                        | M    |
| **P1** | Briefing **editions** per completed run with model-written prose (`GET /api/workspaces/{id}/editions/`, `/{date}/`). Funnel/papers/exclusions already exist as data; `build_pipeline_run_digest_payload` (tasks/auxiliary/email_digest.py) assembles the exact context today; `NarrativeReport`/`ReportingNode` are the stubbed hooks (`/api/reports/` is empty in every deployment — nothing creates rows). | [`src/app/bff/briefings/`](../src/app/bff/briefings/README.md)                                                  | M    |
| **P2** | Chat upgrades: `citations` SSE event for workspace scope; `id:`/heartbeats; cancel generation on client disconnect; **owner-scoped**, paginated sessions; PATCH rename that actually saves.                                                                                                                                                                                                                  | [`src/app/bff/chat/`](../src/app/bff/chat/README.md)                                                            | M    |
| **P2** | Per-user digest preference (`GET/PUT /api/workspaces/{id}/preferences/` → `{digest_email}`).                                                                                                                                                                                                                                                                                                                 | [`src/app/bff/settings/`](../src/app/bff/settings/README.md)                                                    | S    |
| **P2** | Workspace scoring, read-only (`GET /api/workspaces/{id}/scoring/` → snippet + variables + structured weights).                                                                                                                                                                                                                                                                                               | [`src/app/bff/scoring/`](../src/app/bff/scoring/README.md)                                                      | S    |
| **P3** | Pagination + `?ordering=` on `/api/workspaces/` and `/api/pipeline-runs/`.                                                                                                                                                                                                                                                                                                                                   | [`workspaces`](../src/app/bff/workspaces/README.md) · [`pipeline-runs`](../src/app/bff/pipeline-runs/README.md) | S    |

## Backend findings

Observations from the read-only survey that shaped this contract — flagged
because your team will want to triage them (file references from
`backend/` at commit state of 28 Aug 2026):

1. **High — credentials and tokens persisted into a user-readable log.**
   `api/middleware.py` (UserActionAuditMiddleware) stores the raw request
   body of every `/api/` write into `UserActivityLog.input_params` and any
   response body < 4000 bytes into `output_summary`. That captures plaintext
   passwords for `/api/auth/login/` and `/api/auth/change-password/`, and
   the login response's `access`/`refresh` JWTs — all readable via
   `GET /api/activity-logs/`. Redact `password*`, `access`, `refresh`,
   `api_key`, or skip auth endpoints entirely.
2. **High — unrestricted writes.** `PaperViewSet`, `WorkspaceViewSet`,
   `ReportViewSet`, `ExtractionViewSet`, `HITLViewSet` are full
   ModelViewSets behind `IsAuthenticated` only: any member (any role) can
   PUT/PATCH/DELETE papers, the workspace itself (criteria, limits, name —
   and DELETE cascades everything), and reports. Only scrapers enforce roles.
3. **Medium — chat sessions are workspace-scoped, not owner-scoped.** Any
   member can list, read, append to (via `session_id`), and delete another
   member's sessions (`chat/views/session.py`).
4. **Medium — no token revocation.** Password change keeps existing JWTs
   valid; no logout/blacklist; 1-day non-rotating refresh tokens. Consider
   `token_blacklist` + rotation + a logout endpoint. Also
   `AUTH_PASSWORD_VALIDATORS` are not applied on the change endpoint.
5. **Medium — inconsistent error shapes.** `{error}`, DRF field errors,
   `{message}`, and serializer errors on 401 refresh coexist; a problem+json
   `EXCEPTION_HANDLER` fixes this for old and new endpoints at once.
6. **Medium — unbounded lists.** No `DEFAULT_PAGINATION_CLASS`; `/api/papers/`
   returns the entire membership-scoped table with all metrics nested; no
   `?workspace=` on papers/extractions/reports.
7. **Low** — sessions PATCH silently no-ops (all-read-only serializer);
   the chat generator keeps running after client disconnect (LLM cost);
   `GET /health/diagnostics/` is unauthenticated, calls Gemini, leaks the
   GCP service account/bucket/DB counts, and returns HTTP 207 when degraded;
   `DEBUG` defaults to true; the hardcoded `SECRET_KEY` fallback signs JWTs;
   `Paper.signal_score` exists on the model but is not serialized (the
   scorecard endpoint supersedes this).

## Deployment

See [`docs/deploy-handoff.md`](deploy-handoff.md) for the frontend image,
`manifest.yml` env block, and smoke checks.
