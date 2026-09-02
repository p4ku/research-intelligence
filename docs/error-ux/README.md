# Error-UX audit — the deferred items

The 2026-09-01 error-UX audit selected 12 offenses and shipped them in five PR
batches (#18, #24, #26, #27, #34). This folder holds the review page for the
**32 findings ranked below that line** — the confirmed-but-deferred backlog.

| File | What it is |
|---|---|
| `deferred-items.html` | One card per deferred finding, grouped by product area, with a small mock of the *proposed* state where the item is visual (today-vs-proposed side by side where that helps). Statuses are as of 2026-09-02: three items were resolved by later work, four are partial, two are blocked on backend questions. |

Open it directly in a browser (`open docs/error-ux/deferred-items.html`) —
plain static file, no build step, no network access.

## How to use it

Tick the items you want done and press **Copy selection** — it produces a
short list keyed by stable IDs (`D01`–`D32`) that can be pasted into an issue,
a message, or a Claude session to scope the next pass. Mock copy is shown in
English; the shipped product copy would be German-first like the rest of the
app.

The full audit evidence (per-offense problem/evidence/fix/acceptance) and the
batch-execution runbook live in the git-excluded `local-docs/` folder of the
working checkout, not in this repo.
