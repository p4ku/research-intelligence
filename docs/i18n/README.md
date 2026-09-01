# German / English (i18n) — audit, evidence, and how to redo it

Reusable review pages from the 2026-09-01 DE/EN audit. Open the HTML files
directly in a browser (`open docs/i18n/audit.html`) — they are plain static
files with relative image paths, no build step and no network access.

| File | What it is |
|---|---|
| `audit.html` | The full audit: mechanics findings (P0/P1/P2), the German and English word-choice tables, backend language handling, and what was already right. Screenshots in it are the **pre-fix** state. |
| `before-after.html` | The P0 pass screen by screen, German UI, before vs after. |
| `../i18n-backlog.md` | **The live to-do list** (P1/P2). The two HTML pages are the reasoning; this is what gets worked off. |
| `shots/` | The captured evidence, one directory per run (see below). |

## The screenshot sets

Captured with `frontend/scripts/screenshots.ts` against a local Next server
pointed at the **prod-snapshot replay** (`local-data/sri-prod-2026-08-31`), so
they show real data without touching production.

| Set | Language | Viewport | Code state |
|---|---|---|---|
| `shots/de-before/` | German | desktop 1440×900 | `main @ e78847e` (pre-fix) |
| `shots/de-after/` | German | desktop 1440×900 | after the P0 pass (PR #16) |
| `shots/en-before/` | English | desktop 1440×900 | `main @ e78847e` |
| `shots/de-mobile-before/` | German | mobile 390×844 | `main @ e78847e` |

Each set has `desktop/` (or `mobile/`) PNGs, an `index.html` contact sheet, and
a `manifest.json` recording the URL, capture time, per-shot HTTP status and
**horizontal overflow in px** — that last field is the evidence behind the
German mobile-overflow item (P1.6 in the backlog).

## Regenerating them

Full detail in the `screenshots` skill (`.claude/skills/screenshots`) and
`local-docs/snapshot-replay.md`. In short, from `frontend/`:

```bash
# 1. Replay backend on :8010 (any credentials log in)
bun run snapshot:serve

# 2. Your own server — pick an unused BUILD_DIR/PORT pair
BUILD_DIR=.next-agent9 PORT=3009 SITE_URL=http://localhost:3009 \
  BACKEND_INTERNAL_URL=http://localhost:8010 bun run dev

# 3. Capture (add --lang en / --viewports mobile as needed)
bun run screenshots --url http://localhost:3009 --lang de --viewports desktop \
  --out ../docs/i18n/shots/de-after
```

Afterwards run `git checkout -- frontend/tsconfig.json` — Next rewrites it on
every build with `BUILD_DIR` set, and it must not be committed.

Note that `frontend/screenshots/` is git-ignored on purpose (it is the script's
default scratch output). The sets here are committed deliberately, as the
evidence attached to this audit — keep them small and dated rather than
refreshing them in place, so the before/after comparison stays meaningful.

## Checking translation coverage

The dictionary check from the audit is now a normal test:

```bash
cd frontend && bun test src/lib/i18n.test.ts
```

It fails on strings used via `t()` that have no German entry, on the same key
carrying different values in two area modules, and on `{placeholder}`
mismatches. It also prints a count of keys with no static caller (dynamic
labels plus genuinely dead prototype keys — backlog item P1.7).
