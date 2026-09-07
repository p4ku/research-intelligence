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

## Django endpoints we want

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
full `Stars` object after the change. Idempotent (starring twice is fine).
Suggested mapping: a `Star` model `(user, kind, object_id)` with a unique
constraint, `kind` limited to `paper` / `pipeline_run`; 404 when the paper or
run is not visible to the user. P2, size S.

## How it works today

`stub` (default): the set lives in one httpOnly cookie (`rs-stars`, one year,
`src/lib/bff/stars/cookie.ts`) — per browser, not per account, and capped at
80 papers / 30 briefings (oldest dropped) so it fits a 4 KB cookie. Good
enough for demos and replay; not shared across devices.

The star **UI** can be hidden per browser by the `stars` demo flag
(`docs/design/feature-flags.md`): with it off the sidebar layout does not call
this service at all and seeds the store with `emptyStars`, while these routes
stay live and the `rs-stars` cookie is deliberately left intact — so flipping
the flag back on restores the same stars on the next refresh.

## Flip the flag

`BFF_SOURCE_STARS=django` once the endpoint exists. No UI change: the store
and the toggles only ever talk to `/bff/stars`.

## curl

```bash
curl -s localhost:3000/bff/stars -b "sri_access=…"
curl -s -X PUT localhost:3000/bff/stars -b "sri_access=…" \
  -H 'content-type: application/json' \
  -d '{"kind":"paper","id":"8c9a1a2e-5b1d-4c0e-9d5a-7f1e3b2c4d5e","starred":true}'
```

## Done criteria

`contract:check` PASS for `stars.get.desired` and `stars.set.desired`; the
default in `src/lib/bff/core/source.ts` flipped to `django`; the cookie codec
deleted.
