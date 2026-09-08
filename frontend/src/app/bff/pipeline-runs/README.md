# pipeline-runs

## Purpose

Home's Recent Briefings (the five newest briefings across the user's domains,
with their search window, status and counters, plus any run in flight or a
domain's latest failure) and its Start New Briefing form;
briefing editions are derived from completed runs. The "latest completed
run" is the Current briefing.

## BFF routes

| Route                           | Query                                                                                                 | Returns                             |
| ------------------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------- |
| `GET /bff/pipeline-runs`        | `workspace_id` (optional; absent = every domain the user belongs to), `status`, `page`, `page_size`   | `PipelineRunPage`                   |
| `POST /bff/pipeline-runs/start` | body `StartPipelineRun`: `workspace_id`, optional `start_date` / `end_date` (YYYY-MM-DD, end ≥ start) | `201 StartedPipelineRun` (`run_id`) |

Schema: `src/lib/bff/pipeline-runs/schema.ts` (`PipelineRun` — the contract
trims Django's serializer to what the UI shows).

## Django endpoint we want

`GET /api/pipeline-runs/?workspace=&status=` — the existing endpoint (already
filterable), paginated with `?ordering=`. Low priority (P3).

## Current implementation

`django` (default): the bare array, validated (`upstream.ts`), trimmed and
normalised (unknown statuses → `pending`). The search window comes from the
serializer's `configuration_override` (`period_start` / `period_end` /
`lookback_days`; all null on captures that predate the field).

Starting a run calls `POST /api/pipeline-runs/start/` with `workspace_id`,
`start_date`, `end_date` and `autonomous: true`. Django creates the run as
`running` and dispatches the first stage before answering, so the run is
already in the list when the response lands. Membership (`admin`, `manager`,
`researcher`) refusals arrive as 403 → `forbidden`; a quota refusal is a 400
whose `error` becomes the problem's `detail`. Django does not serialise
starts: "one run at a time" is enforced by this route (409 `conflict` while
any run is `running` / `pending`) and by the form, which is disabled while
Home shows a run in flight.

## curl

```bash
curl -s "localhost:8000/api/pipeline-runs/?workspace=$WS&status=completed" -H "authorization: Bearer $TOKEN"
curl -s "localhost:3000/bff/pipeline-runs?workspace_id=$WS&status=completed" -b "sri_access=…"
curl -s -X POST localhost:3000/bff/pipeline-runs/start -b "sri_access=…" -H 'content-type: application/json' \
  -d '{"workspace_id":"'$WS'","start_date":"2026-08-01","end_date":"2026-09-05"}'
```

## Done criteria

Pagination lands → `contract:check` PASS for `pipeline-runs.list.desired`.
