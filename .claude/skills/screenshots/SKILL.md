---
name: screenshots
description: Capture every screen of the Next.js app at mobile and desktop widths with Playwright (frontend/scripts/screenshots.ts). Use when the user asks for screenshots/snapshots of the app, a visual pass over all pages, before/after shots of a UI change, or a responsive (mobile) check.
---

# Screenshot every screen (mobile + desktop)

`frontend/scripts/screenshots.ts` logs in, discovers the dynamic routes, and
captures all screens per viewport into `frontend/screenshots/<stamp>/`. It also
writes `manifest.json`, an `index.html` contact sheet (mobile and desktop side
by side), and updates the `frontend/screenshots/latest` symlink. Output is
git-ignored.

Screens: login `/`, `/dashboard`, mobile nav drawer open, `/briefing`,
`/briefing/[date]`, `/briefing/[date]/run`, `/papers`, `/papers/[id]`,
`/scoring`, `/ask`, `/settings`. `[date]` and `[id]` come from the first link on
the list page. Viewports: `mobile` 390×844 @2x, `desktop` 1440×900 @1x
(`tablet` 834×1194 is available but off by default).

## 1. Make sure an app is running

The script needs a Next.js server; it does not start one. Check first:

```bash
lsof -nP -iTCP:3009 -iTCP:3010 -iTCP:8010 -iTCP:8011 -sTCP:LISTEN
```

- Something on `3009`/`3010` → use it (`--url http://localhost:<port>`). It may
  belong to another session; only read from it, never kill or restart it.
- Nothing → start your own, on your own `BUILD_DIR`/`PORT` (see the
  `build-management` skill), against the replay backend if `8010` is up, or
  a real Django (`8011`). Follow `local-docs/snapshot-replay.md` and
  `local-docs/working-in-this-repo.md`. Afterwards run
  `git checkout -- frontend/tsconfig.json` (Next rewrites it).
- A deployed target works too, e.g. `--url https://sri-prod.apps.01.cf.eu01.onstackit.cloud`
  with real credentials via env (see below). Prefer the replay for design work.

Credentials: default `admin` with a dummy password — the replay server accepts
any credentials, so against the replay no setup is needed. Against a real
Django, export `SCREENSHOT_PASSWORD` in the shell first (value in
`local-docs/backend-frontend-seam.md`); never print or paste a password into
the chat or put it on a visible command line.

## 2. Run it

From `frontend/` (deps must be installed: `bun install --frozen-lockfile`;
Playwright's Chromium downloads on first use via `bunx playwright install chromium`
if it's missing):

```bash
cd frontend
bun run screenshots                               # http://localhost:3009, mobile + desktop, full page
bun run screenshots --url http://localhost:3010   # another server
bun run screenshots --viewports desktop           # one viewport (mobile|tablet|desktop)
bun run screenshots --routes papers,paper-detail  # subset, by screen name (login, dashboard, nav-open, briefing, briefing-edition, briefing-run, papers, paper-detail, scoring, ask, settings). Avoid the /papers/[id] route form — zsh globs the brackets.
bun run screenshots --lang de                     # German UI (sets the rs-lang cookie)
bun run screenshots --theme dark                  # adds .dark to <html>
bun run screenshots --no-full-page                # viewport-only captures
bun run screenshots --out /path/to/dir            # custom output dir (relative = from frontend/; `latest` only updates for dirs under frontend/screenshots/)
bun run screenshots --headed                      # watch it
```

A full run takes ~1–2 minutes. Run it in the foreground with a generous
timeout (≥ 300 s) or in the background and wait for it.

## 3. Read the result

The log prints one line per shot. Look for:

- `FAIL …` — the page errored or the session was rejected (redirect to `/`).
- `⚠ HTTP 4xx/5xx` — the route returned an error page; the image shows it.
- `↔ overflows by Npx` — the document is wider than the viewport: a real
  responsive bug (the image is clipped to the viewport width; the manifest
  has `overflowX`). Report these to the user even if they didn't ask.
- `✂ cut at …` — the page was taller than Chromium's capture limit.
- `skip …` — no `[date]`/`[id]` link found (empty workspace); the manifest
  records the reason.

Exit code is non-zero if login failed or any shot failed or returned ≥ 400 —
but `skip` (missing `[date]`/`[id]` data) still exits 0, so also check the
manifest's `error` fields before declaring the run complete.

Then inspect the images. `frontend/screenshots/latest/index.html` is the
quickest overview for a human (open it in a browser). For your own review:

- Read individual PNGs with the Read tool: `frontend/screenshots/latest/<viewport>/NN-<name>.png`.
- Do not eyeball all ~20 images in the main context. Fan out subagents,
  ~5–8 images each, and have them return a per-image verdict: error text or
  empty states, clipped/overlapping content, horizontal scroll, unreadable
  text at mobile width, anything that contradicts the intended design.
- Mobile images are 2× (780 px wide); full-page ones can be very tall — that
  is expected.

## 4. Before/after comparisons

Each run gets its own timestamped folder, so capture, change the code, capture
again, and compare the two folders. File numbers are stable (each screen keeps
its number across runs, viewports and `--routes` subsets, with gaps where
screens are skipped), but join runs on `manifest.json` (`name` + `viewport`),
not on eyeballed filenames. `--out` names a folder meaningfully, e.g.
`--out screenshots/before-tabs-fix` (relative to `frontend/`; dirs under
`frontend/screenshots/` also move the `latest` symlink — so for before/after
work review the two named folders directly, not `latest`).

## Gotchas

- `frontend/screenshots/` is git-ignored — never commit captures.
- Dev-server captures hide the Next.js dev badge automatically; a stray dark
  circled "N" in a corner means that failed — mention it, don't treat it as UI.
- Data drifts: a dev server against the real Django shows `test_e2e_*`
  workspaces created by the e2e suite. The replay (`8010`) is the cleaner dataset.
- Ask and Settings are read-only on the replay (writes → 501); the script only
  reads, so that's fine.
- To add a screen, append to `SCREENS` in `frontend/scripts/screenshots.ts`
  (`interact` runs before the shot; `only` limits viewports; `viewportOnly`
  disables full-page for overlays).
- `frontend/.claude/skills/retake-screenshots` is a leftover from the
  predecessor repo (rs.adder.dev, `scripts/screenshot-pages.sh`) and does not
  apply here — use this skill.
