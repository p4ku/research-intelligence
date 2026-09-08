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

## Django endpoints we want

- `GET /api/workspaces/{workspace_id}/editions/?page=&page_size=` →
  `{count,next,previous,results: BriefingEditionSummary[]}`
- `GET /api/workspaces/{workspace_id}/editions/{date}/?run_id=` → `BriefingEdition`
  (the run's edition, else the day's latest run)

The decisive addition is the **prose**: `title` and `in_brief` written by the
reporting step per completed run, `in_brief_source: "model"`. Everything else
(funnel, papers, exclusions) already exists as data. Starting points on your
side: `build_pipeline_run_digest_payload`
(`research_intelligence/tasks/auxiliary/email_digest.py`) already assembles
exactly this context for the digest email; `NarrativeReport` +
`ReportingNode` (`tasks/step_8_reporting/`) are the stubbed persistence/
generation hooks — note `/api/reports/` is empty in every deployment today
because nothing creates `NarrativeReport` rows.

## Current implementation

`composed` (default): `service.ts` reads
`GET /api/pipeline-runs/?workspace=&status=completed` and the scored corpus,
and `compose.ts` (pure, tested) turns them into editions —
surfaced = passed papers of the run (signal-first), exclusions = rejected/
withdrawn papers with their `screening_reasoning`, funnel = the run's
counters. `title`/`in_brief` come from `prose.ts` templates filled with real
numbers and titles, flagged `in_brief_source: 'template'` (the UI shows an
"auto-brief" tag). `stub` serves `fixtures.ts`.

A run's papers are read from each paper's own `metrics[]` row for that run
(`src/lib/papers/runs.ts`), not from the paper-level `pipeline_run`: the
paper serializer collapses a paper to the newest run that saw it, which would
empty every older briefing in a domain. A row without `screening_status`
(a deployment whose metric serializer predates the field) falls back to the
paper's current status. Under `BFF_SOURCE_PAPERS=django|stub` there is no
run index, so attribution falls back to the paper-level `pipeline_run`: an
older same-day run then composes with no papers, and Home and the archive
leave it out (the list endpoint still serves it).

When the counters and the corpus still disagree — the run passed papers the
edition cannot show — the prose says so ("Papers not on file") instead of
claiming none passed, and Home and the archive treat the run as having no
briefing to open.

## Flip the flag

`BFF_SOURCE_BRIEFINGS=django` once both endpoints exist.

## curl

```bash
curl -s "localhost:3000/bff/briefings?workspace_id=$WS" -b "sri_access=…"
curl -s "localhost:3000/bff/briefings/2026-08-31?workspace_id=$WS" -b "sri_access=…"
# Desired:
curl -s "localhost:8000/api/workspaces/$WS/editions/" -H "authorization: Bearer $TOKEN"
```

## Done criteria

1. `contract:check` PASS for `briefings.list.desired` + `briefings.detail.desired`.
2. Prose is model-written (`in_brief_source: "model"`) and the "auto-brief"
   tag disappears; fixtures refreshed from a real edition.
3. Default flipped to `django`; `prose.ts` and the composition retire.
