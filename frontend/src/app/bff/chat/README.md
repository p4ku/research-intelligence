# chat

## Purpose

Corpus-wide Q&A (**Ask**, `/ask`) and the per-paper conversation on the paper
detail page — streamed answers with visual citations, a fact-check verdict,
and server-side session history.

The `/ask` **UI** can be hidden per browser by the `ask` demo flag; these
routes are **not** flag-gated and must stay that way. The cookie is a
preference the visitor owns, not an authorization boundary, Django's
`/api/chat/*` is reachable through the proxy rewrite regardless, and the
stream is the one surface where a mid-response behaviour change cannot be
recovered. The per-paper sidecar keeps calling them with the flag off
(`docs/design/feature-flags.md` §4.3).

## What the UI needs

- Streamed answer text; the session/message ids (continuity + the rail).
- **Citations as objects** (`{paper_id, title, signal_score, href}`) — enough
  to render a citation card without a second lookup.
- Visual citations (page · figure label · quote · verified tick) and the
  fact-check summary (grounding score, PASS/WARNING).
- Sessions for the history rail: list (newest first), open (turns), delete,
  rename.

## BFF routes

| Route                                                   | Notes                                                                                                                                                                                   |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /bff/chat/stream`                                 | Body `ChatStreamRequest` `{question, workspace_id \| paper_id, session_id?, deep_thinking?}` (exactly one scope id). Response: SSE (below). Pre-stream failures are plain problem+json. |
| `GET /bff/chat/sessions?workspace_id=\|paper_id=&page=` | `ChatSessionPage`                                                                                                                                                                       |
| `GET /bff/chat/sessions/{id}`                           | `ChatSessionDetail` — `turns[]`, one per Q+A                                                                                                                                            |
| `DELETE /bff/chat/sessions/{id}`                        | 204                                                                                                                                                                                     |
| `PATCH /bff/chat/sessions/{id}`                         | **501** until Django's rename saves (see below)                                                                                                                                         |

### Our SSE contract (also what we request of Django)

Frames `id: <n>\nevent: <name>\ndata: <one-line JSON>\n\n`; `: ping <iso>`
comments every 15 s. Events, in order:

| Event              | Payload                                                                                                                                                     |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `metadata`         | `{message_id, session_id, scope: {workspace_id, paper_id}}`                                                                                                 |
| `citations`        | `{items: PaperCitation[]}`                                                                                                                                  |
| `delta`            | `{text}` — raw model text; inline `[Page N, Fig X, box_2d: […], quote: "…"]` markers arrive verbatim (split across frames) and the UI renders them as chips |
| `visual_citations` | `{items: [{page?, label?, box_2d?, quote?, verified_in_source?}]}` — one entry per distinct inline marker, in order of first appearance                     |
| `fact_check`       | `{verified, grounding_score, verified_count, total_count, status}`                                                                                          |
| `usage`            | `{tokens_in, tokens_out, total_tokens, usd_cost: number}`                                                                                                   |
| `done`             | `{message_id, session_id}`                                                                                                                                  |
| `error`            | a Problem object; ends the stream                                                                                                                           |

Schemas: `src/lib/bff/chat/schema.ts` (`ChatEvent`).

## Django endpoints we want

The chat backend **exists and works** — these are upgrades to
`POST /api/chat/stream/` and `/api/chat/sessions/`:

1. **`citations` event** for workspace-scope answers: which papers grounded
   the answer, as `{paper_id, title, signal_score}`. (Paper-scope streams are
   covered — the BFF synthesises the one citation from the session's paper.
   `PaperChatMessage.citations` is never populated today; either populate it
   or emit the event.)
2. **Stream hygiene**: `id:` lines, `: ping` heartbeats (≤15 s), problem+json
   `error` payloads. _Disconnect is handled (11 Sep 2026): the provider stream
   is closed, and the words that had arrived are filed under status `aborted`
   and billed — the UI shows them with a "Stopped" line._
3. **Sessions**: paginate, and scope to the **owner** in the queryset — the
   list is owner-scoped for researchers (admins/managers see the workspace;
   the BFF filters `mine=1` after the rows arrive). Appending to a colleague's
   session is a 403, and a `session_id` from another paper a 400.
4. **Rename**: `PATCH /api/chat/sessions/{id}/ {title}` currently returns 200
   without saving (all-read-only serializer). Make it save; the BFF's PATCH
   answers 501 until then.
5. **Citations on the stream**: _fixed — `visual_citations` streams after
   `verify()`, so live chips carry `verified_in_source`._ The flag is `null`
   (no tick, no cross) when the backend had no body text to check against:
   most of the corpus is URL-only papers, where the model sees the abstract
   alone; the `fact_check` frame then says `SKIPPED_NO_SOURCE_TEXT`. On the
   stored-PDF path the body is extracted server-side for the check only.
   Longer term, strip the inline markers server-side (`citations.py` parses
   but keeps them) and carry citation positions in the contract — then the
   UI's marker regex (`src/lib/chat/citation-markers.ts`) can go. Until then
   the backend must **not** strip them silently: the chips depend on them.

## Current implementation

Source `django` (default): `stream/route.ts` re-frames Django's SSE
(`src/lib/bff/chat/reframe.ts`, parser `src/lib/sse/parse.ts`); sessions are
normalised in `src/lib/bff/chat/service.ts` — **one Django message row = one
turn** (it holds `question` + `message`; `sender` is always `'user'`).
`stub` replays `fixtures.ts` frames with delays for offline UI work.

Known upstream quirks the service already absorbs: `usd_cost` is a Decimal
_string_ on messages but a number on the `usage` frame; `hallucination_guard`
may be `{}`; `visual_citations` items are loosely shaped.

## curl

```bash
# Stream (note: POST — EventSource cannot be used):
curl -N localhost:8000/api/chat/stream/ -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d "{\"question\":\"What does this paper enable?\",\"paper_id\":\"$PAPER\"}"
# Through the BFF (session cookie), with ids + pings:
curl -N localhost:3000/bff/chat/stream -b "sri_access=…" \
  -H 'content-type: application/json' -d '{"question":"…","workspace_id":"…"}'
curl -s "localhost:8000/api/chat/sessions/?workspace_id=$WS" -H "authorization: Bearer $TOKEN"
```

## Done criteria

1. `bun run contract:check` PASS for `chat.sessions.desired` and
   `chat.rename.desired`; the stream upgrades verified with `curl -N`
   (ids, pings, `citations` event on a workspace-scope question).
2. Owner scoping confirmed (member B cannot read member A's sessions).
3. `BFF_SOURCE_CHAT` stays `django`; the BFF's citations synthesis and the
   501 rename branch are removed.
