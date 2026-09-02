# workspaces

## Purpose

The top-level scope selector (sidebar switcher), definition metadata for the
papers views, and the Settings workspace card.

## What the UI needs

`id`, `name`, the caller's `user_role`, the extraction definitions
(name/key/active/TRL/scale), scrapers (provider + query), digest schedule,
LLM model.

## BFF routes

| Route                 | Query               | Returns         |
| --------------------- | ------------------- | --------------- |
| `GET /bff/workspaces` | `page`, `page_size` | `WorkspacePage` |

Schema: `src/lib/bff/workspaces/schema.ts` (`Workspace`). The BFF derives
`definitions[].key/is_trl/max` from the raw serializer.

## Django endpoint we want

`GET /api/workspaces/` — the existing endpoint, paginated
(`{count,next,previous,results}`) with `?ordering=`. Low priority (P3): bare
arrays are tolerable at workspace counts. Nice-to-have on the way past:
include each definition's `exit_metric` key (currently unserialized), which
would remove a whole class of frontend derivation.

## Current implementation

`django` (default): today's bare array via `src/lib/bff/workspaces/service.ts`,
validated (`upstream.ts`) and normalised into the contract shape.

## curl

```bash
curl -s localhost:8000/api/workspaces/ -H "authorization: Bearer $TOKEN" | jq '.[0] | keys'
curl -s "localhost:3000/bff/workspaces" -b "sri_access=…"
```

## Done criteria

Pagination lands on `/api/workspaces/` → `contract:check` PASS for
`workspaces.list.desired`; the service's array/envelope branch flips.
