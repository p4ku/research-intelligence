# stars

## Purpose

The analyst's stars: one star per paper and one per briefing, the MVP's only
front-end curation (no collections, folders or notes). Feeds the star toggles
on `/briefing/[date]` (rows and header), `/papers`, `/papers/[id]` and the
`/briefing` archive, and the **Starred** filter on each list.

The `/papers` consumer is behind the `all_papers` demo flag
(`src/lib/features.ts`): when the corpus list is hidden, the stars it carries
go with it. The routes below are not flagged and keep serving.

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

`backend/api/views/stars.py`, model `Star(user, kind, paper?, pipeline_run?)`.

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
twice is fine). 404 when the paper or run is not in one of the user's
workspaces, 400 on a bad body, 401 without a token.

## How it works

`django` is the only source: the BFF passes both routes through to
`/api/stars/` and validates the shape, so stars belong to the account, not the
browser. The sidebar layout reads the set once per shell render and seeds the
client store; a read failure is "nothing starred", never a broken shell.
Snapshot replay (`bun run snapshot:serve`) keeps stars in memory so the
toggles work against a capture too.

Until this flip the set lived in a per-browser `rs-stars` cookie, so it
survived sign-out and the next person on that browser inherited it. Stars
saved there were deliberately not migrated: nothing reads the cookie any more,
and it expires on its own.

The star **UI** can be hidden per browser by the `stars` demo flag
(`docs/design/feature-flags.md`): with it off the sidebar layout does not call
this service at all and seeds the store with `emptyStars`, while these routes
stay live and the rows in Django are untouched — so flipping the flag back on
restores the same stars on the next refresh.

## curl

```bash
curl -s localhost:3000/bff/stars -b "sri_access=…"
curl -s -X PUT localhost:3000/bff/stars -b "sri_access=…" \
  -H 'content-type: application/json' \
  -d '{"kind":"paper","id":"8c9a1a2e-5b1d-4c0e-9d5a-7f1e3b2c4d5e","starred":true}'
```
