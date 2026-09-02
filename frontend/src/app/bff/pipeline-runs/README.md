# pipeline-runs

## Purpose

The dashboard's "latest completed run": funnel counters
(`total_papers_fetched` → `total_papers_passed_screening` → surfaced) and the
run date; briefing editions are derived from completed runs.

## BFF routes

| Route                                 | Query                                                                                                 | Returns                                                                                                                                          |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /bff/pipeline-runs`              | `workspace_id` (optional; omit for every workspace the caller can see), `status`, `page`, `page_size` | `PipelineRunPage`                                                                                                                                |
| `GET /bff/pipeline-runs/overview`     | —                                                                                                     | `PipelineRunsOverview`: the newest 500 runs across workspaces plus the workspaces themselves, one payload for `/studio/overview` and its polling |
| `GET /bff/pipeline-runs/{id}/edition` | —                                                                                                     | `BriefingEdition` composed for that run (404 when it has none; only completed runs have one)                                                     |

Schema: `src/lib/bff/pipeline-runs/schema.ts` (`PipelineRun` — the contract
trims Django's serializer to what the UI shows).

## Django endpoint we want

`GET /api/pipeline-runs/?workspace=&status=` — the existing endpoint (already
filterable), paginated with `?ordering=`. Low priority (P3).

## Current implementation

`django` (default): the bare array, validated (`upstream.ts`), trimmed and
normalised (unknown statuses → `pending`).

## curl

```bash
curl -s "localhost:8000/api/pipeline-runs/?workspace=$WS&status=completed" -H "authorization: Bearer $TOKEN"
curl -s "localhost:3000/bff/pipeline-runs?workspace_id=$WS&status=completed" -b "sri_access=…"
```

## Done criteria

Pagination lands → `contract:check` PASS for `pipeline-runs.list.desired`.
