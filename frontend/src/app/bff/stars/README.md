# stars

## Purpose

The analyst's stars: one star per paper and one per briefing, the MVP's only
front-end curation (no collections, folders or notes). Feeds the star toggles
on `/briefing/[date]` (rows and header), `/papers`, `/papers/[id]` and the
`/briefing` archive, and the **Starred** filter on each list.

## What the UI needs

- **Read once per page**: the full set of starred paper ids and briefing
  (pipeline-run) ids for the signed-in user. The sidebar layout loads it and
  hands it to a client store (`src/lib/stars-client.tsx`), so every star on
  the page toggles instantly.
- **Write one at a time**: star / unstar a record, optimistic in the UI, the
  full set echoed back so the store never drifts.

## BFF routes

| Route            | Body                                                      | Returns |
| ---------------- | --------------------------------------------------------- | ------- |
| `GET /bff/stars` | —                                                         | `Stars` |
| `PUT /bff/stars` | `StarUpdate` `{kind: "paper" \| "briefing", id, starred}` | `Stars` |

Schemas: `src/lib/bff/stars/schema.ts`. Errors are problem+json.

## Django endpoints

Shipped in PR #60 (`backend/api/views/stars.py`, model `Star(user, kind,
paper?, pipeline_run?)`, 23 tests in
`research_intelligence/tests/test_stars_api.py`).

### `GET /api/stars/`

The **calling user's** stars:

```json
{
  "papers": ["8c9a1a2e-5b1d-4c0e-9d5a-7f1e3b2c4d5e"],
  "briefings": ["00000000-0000-4000-8000-000000000031"]
}
```

`briefings` holds pipeline-run ids: one briefing edition per completed run,
which is also how the frontend addresses editions today.

### `PUT /api/stars/`

Body `{"kind": "paper", "id": "<uuid>", "starred": true}`; responds with the
full `Stars` object after the change, oldest star first. Idempotent (starring
twice is fine; a re-star moves the id to the end). 404 when the paper or run is
not in one of the user's workspaces, 400 on a bad body, 401 without a token.

## How it works

`django` is the only source: the BFF passes both routes through to
`/api/stars/` and validates the shape. The sidebar layout reads the set once
per shell render and seeds the client store; a read failure is "nothing
starred", never a broken shell. Snapshot replay (`bun run snapshot:serve`)
keeps stars in memory so the toggles work against a capture too.

## curl

```bash
curl -s localhost:3000/bff/stars -b "sri_access=…"
curl -s -X PUT localhost:3000/bff/stars -b "sri_access=…" \
  -H 'content-type: application/json' \
  -d '{"kind":"paper","id":"8c9a1a2e-5b1d-4c0e-9d5a-7f1e3b2c4d5e","starred":true}'
```

## Status

Done. `contract:check` PASS for `stars.get.desired` (`stars.set.desired` shows
SKIP: the checker never executes writes, so the PUT is covered by the backend
test suite and the curl above); the default in `src/lib/bff/core/source.ts` is
`django`; the cookie stub is gone.
