# component-runs

## Purpose

The Studio's run detail (`/studio/runs/[id]`): the per-step timeline of one
pipeline run — what each step did, how long it took, what it cost, and why it
failed.

## BFF routes

| Route                     | Query                                             | Returns            |
| ------------------------- | ------------------------------------------------- | ------------------ |
| `GET /bff/component-runs` | `pipeline_run_id` (required), `page`, `page_size` | `ComponentRunPage` |

Schema: `src/lib/bff/component-runs/schema.ts` (`ComponentRun`).

## Django endpoint we want

`GET /api/component-runs/?pipeline_run=` already exists and is already
filterable by `pipeline_run`, `step_type` and `status`. Pagination and
`?ordering=` would be nice-to-have (P3); nothing is blocked without them.

## Why this resource normalises

`ComponentRun.metrics` is free-form engine JSON with no stable schema. The
same number arrives under different keys depending on step and engine version
— `search` alone writes all five of `duplicates`, `duplicates_count`,
`total_duplicates`, `duplicates_skipped` and `total_duplicates_skipped`. The
service resolves that once into `summary`, a discriminated union keyed by step
type, so no component re-derives it. Two rules it holds to:

- **`summary.kind === 'none'` means the step recorded nothing we recognise.**
  It is not a zero. Real runs skip OCR entirely and write only
  `{"status": "skipped"}`; the UI must say "no metrics recorded", not
  "0 converted". (The Django admin renders `-` here, and renders the same `-`
  for a _successful_ OCR step, which is what prompted this.)
- **`cost` carries measured spend only.** Every field is nullable and stays
  null when the engine did not record it. The admin estimates a cost from
  `screened × 5000 tokens` against a hardcoded model name and renders the
  guess identically to a measurement; on a page used to judge spend that is a
  correctness bug, not a nicety. Only `screening` and `extraction` record
  `usd_cost` today — the other five step types legitimately show no cost.

## curl

```bash
curl -s "localhost:8000/api/component-runs/?pipeline_run=$RUN" -H "authorization: Bearer $TOKEN"
curl -s "localhost:3000/bff/component-runs?pipeline_run_id=$RUN" -b "sri_access=…"
```

## Done criteria

Already `django`. `contract:check` PASS for `component-runs.list.current`.
