# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Django/Celery backend (`backend/`, owned by another engineer) running a literature-review
pipeline over Gemini; Next.js 16 frontend (`frontend/`, ours) reading it through a BFF seam.
Prod is one Cloud Foundry hostname path-routed across the five apps in `manifest.yml`;
`deploy.yml` ships every push to `main`. PRs merge with a merge commit.

If `local-docs/` exists (git-excluded), read its `README.md` first.

## Commands

```bash
# frontend/
bun run check                  # the pre-commit gate; CI does not build or check the frontend at all
bun run build                  # deliberately not in `check`; run after config/routing changes
bun run contract:spec          # after any zod schema change, then commit contract/*.openapi.json (lint diffs them byte-for-byte)
bun test src/lib/papers/select.test.ts
bun run snapshot:pull && bun run snapshot:serve   # prod data replayed on :8010, any creds log in, writes → 501; prefer this to fixtures for UI work

# backend/  (manage.py test, not pytest, despite pytest.ini; SQLite whenever DB_HOST is unset)
./run_tests.sh                                                   # full suite, parallel
./run_tests.sh research_intelligence.tests.test_jwt_auth.Cls.test_name
./run_tests.sh mcp_server
```

`./tests_e2e/run_frontend_e2e.sh` targets **prod** by default; pass `local` or set `E2E_BASE_URL`.

## Non-obvious architecture

- **BFF seam.** Server components import `src/lib/bff/<resource>/service.ts`; client components
  fetch `src/app/bff/<resource>/route.ts`. Each resource has a source `stub | composed | django`
  (`src/lib/bff/core/source.ts`, env `BFF_SOURCE_<RESOURCE>`); flipping a default to `django`
  is the "backend delivered the contract" signal. `GET /bff/status` shows live sources.
- BFF routes live under `/bff`, never `/api`: Cloud Foundry sends `/api/*` straight to Django.
  BFF URLs have no trailing slash; Django URLs require one.
- A Django `Workspace` is the UI's "domain". Pages span every workspace the user belongs to;
  there is no switcher or scope cookie.
- Demo feature flags (`src/lib/features*.ts`) are read only in `page.tsx`/`loading.tsx`
  (`getFeatures`/`requireFeature`) or via `useFeatures()` in client components. Never in
  services, route handlers or the proxy. Off means removed (route 404s), not disabled.
- Pipeline runs are a DAG advanced by `PipelineRunner.tick()` in
  `research_intelligence/tasks/orchestrator/runner.py`; `ResearchAgentProcess` is a legacy
  compatibility wrapper. Scoring/post-processing run user Python in an AST sandbox.

## Conventions

- Frontend branches touch `frontend/` only; `scope:check` fails otherwise. Backend or root
  changes get their own PR that says so.
- Several agents share the checkout: stage by name, never `git add -A`; use a worktree.
- Never commit `frontend/tsconfig.json` (Next rewrites it per `BUILD_DIR`; `git checkout --`
  it), `frontend/local-data/` (prod data), `frontend/screenshots/`.
- `contract/*.openapi.json` and `tsconfig.json` stay in `.prettierignore`.
- Root files (`docker-compose*.yml`, `manifest.yml`) change only when the image contract
  changes; match the `${VAR:-default}`, literal-port, no-commentary style.
- `.github/workflows/README.md` describes CD workflows that do not exist; `ci.yml` and
  `deploy.yml` are the real ones.
