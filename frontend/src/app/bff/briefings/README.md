# briefings

## Purpose

Daily editions: one briefing per completed pipeline run — funnel, the
surfaced papers, the screening log (what screened out and why), and a short
prose brief. Feeds `/briefing`, `/briefing/[date]`, `/briefing/[date]/run`,
and the dashboard's "Today in brief".

## What the UI needs

`date`, `title`, `in_brief` prose (with a flag distinguishing model-written
from template), funnel counters, the surfaced papers (id/title/authors/
source, plus the run's own signal and — still missing from the Django
editions endpoint — its screening status for the paper), and the exclusions
(title/source/screening reason).

## BFF routes

| Route                       | Query                                                                                                    | Returns                               |
| --------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| `GET /bff/briefings`        | `workspace_id` (optional; absent = every domain), `page`, `page_size`                                    | `BriefingEditionPage` (summaries)     |
| `GET /bff/briefings/{date}` | `workspace_id` (optional; absent = every domain), `run_id` (optional; absent = the day's newest edition) | `BriefingEdition` (with `exclusions`) |

Schemas: `src/lib/bff/briefings/schema.ts`. Dates are `YYYY-MM-DD`. A domain
that ran twice in a day has two editions; `run_id` picks one, and without it
the day's newest is served (a `run_id` that did not run that day falls back
the same way). The pages carry it as `/briefing/{date}?domain=&run=`.

## Django endpoints (Implemented & Active)

- `GET /api/workspaces/{workspace_id}/editions/?page=&page_size=` →
  `{count,next,previous,results: BriefingEditionSummary[]}`
- `GET /api/workspaces/{workspace_id}/editions/{date}/?run_id=` → `BriefingEdition`
  (the run's edition, else the day's latest run, including funnel, surfaced papers, exclusions, and brief prose)

These endpoints are implemented in Django `WorkspaceViewSet` (`editions` and `edition_detail` actions) with optimized single-query PaperMetric lookups, scalar field pruning, and timestamp range filtering.

## Current implementation

- `django`: Served natively from the backend editions engine (`WorkspaceViewSet.editions` and `edition_detail`).
  The backend compiles the full edition context: surfaced papers (ordered by signal score), exclusions with screening reasoning, funnel counters, and briefing prose.
- `composed`: `service.ts` reads `GET /api/pipeline-runs/?workspace=&status=completed` and the scored corpus, and `compose.ts` (pure, tested) turns them into editions — surfaced = passed papers of the run (signal-first), exclusions = rejected/withdrawn papers with their `screening_reasoning`, funnel = the run's counters. `title`/`in_brief` come from `prose.ts` templates filled with real numbers and titles, flagged `in_brief_source: 'template'`.
- `stub`: Serves `fixtures.ts`.

## curl

```bash
TOKEN=$(curl -s localhost:8000/api/auth/login/ -H 'content-type: application/json' \
  -d '{"username_or_email":"admin","password":"schwarz123!"}' | jq -r .access)
WS=$(curl -s localhost:8000/api/workspaces/ -H "authorization: Bearer $TOKEN" | jq -r '.[0].id')

# Backend canonical editions:
curl -s "localhost:8000/api/workspaces/$WS/editions/" -H "authorization: Bearer $TOKEN"
curl -s "localhost:8000/api/workspaces/$WS/editions/2026-08-31/" -H "authorization: Bearer $TOKEN"

# BFF:
curl -s "localhost:3000/bff/briefings?workspace_id=$WS" -b "sri_access=…"
curl -s "localhost:3000/bff/briefings/2026-08-31?workspace_id=$WS" -b "sri_access=…"
```

## Status

1. `GET /api/workspaces/{id}/editions/` and `/editions/{date}/` fully implemented and active in backend.
2. Verified with query optimization benchmarks and invariance tests (`test_api_endpoint_optimizations.py`, `test_query_optimization_and_dataset_invariance.py`).
