# pipeline-runs

## Purpose

Home's Recent Briefings (the five newest briefings across the user's domains,
with their search window, status and counters, plus any run in flight or a
domain's latest failure) and its Start New Briefing form;
briefing editions are derived from completed runs. The "latest completed
run" is the Current briefing.

## BFF routes

| Route                                    | Query                                                                                                 | Returns                                                                                                                                              |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /bff/pipeline-runs`                 | `workspace_id` (optional; absent = every domain the user belongs to), `status`, `page`, `page_size`   | `PipelineRunPage`                                                                                                                                    |
| `POST /bff/pipeline-runs/start`          | body `StartPipelineRun`: `workspace_id`, optional `start_date` / `end_date` (YYYY-MM-DD, end ≥ start) | `201 StartedPipelineRun` (`run_id`)                                                                                                                  |
| `POST /bff/pipeline-runs/{run_id}/abort` | path `run_id`                                                                                         | `200 AbortedPipelineRun` (`run_id`, `status: "aborted"`); `409` once the run has ended, `403` unless the caller is an admin or manager of the domain |

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
whose `error` becomes the problem's `detail`. Django admits at most five
runs in flight (`pending` / `running` / `paused`) per workspace and refuses
a search window that is already running — 409 with `code:
run_limit_reached | duplicate_run` → `conflict`, the `error` sentence as
`detail`. This route takes the same verdict first from the live list
(`src/lib/bff/pipeline-runs/admission.ts`, the rule's pure mirror) so a
stale Home gets its 409 without a round-trip; the form uses the same module
to keep Start off only while the chosen domain is full or the chosen window
is running.

Stopping a run calls `POST /api/pipeline-runs/{id}/abort/`; Django marks the
run and its active steps `aborted` and stamps `completed_at`, so the row reads
as ended on the next list. Django answers every refusal with **400** and an
`Error: …` sentence in `error` (the view wraps the bare string its service
layer returns); `abort.ts` re-types the two it makes — "already in status"
→ `409 conflict`, "insufficient workspace permissions" → `403 forbidden` — so
readers get house copy, never the sentence. A run the caller cannot see is
Django's 404, passed through.

## curl

```bash
curl -s "localhost:8000/api/pipeline-runs/?workspace=$WS&status=completed" -H "authorization: Bearer $TOKEN"
curl -s "localhost:3000/bff/pipeline-runs?workspace_id=$WS&status=completed" -b "sri_access=…"
curl -s -X POST localhost:3000/bff/pipeline-runs/start -b "sri_access=…" -H 'content-type: application/json' \
  -d '{"workspace_id":"'$WS'","start_date":"2026-08-01","end_date":"2026-09-05"}'
curl -s -X POST localhost:3000/bff/pipeline-runs/$RUN/abort -b "sri_access=…"
```

## Done criteria

Pagination lands → `contract:check` PASS for `pipeline-runs.list.desired`.
