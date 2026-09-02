# User journeys — frontend walkthrough

Three persona journeys through the reading app, one static HTML page each,
with real screenshots per step and short silent clips where the interaction
matters. Open `index.html` directly in a browser (`open docs/journeys/index.html`);
plain files, relative paths, no build step, no network access.

| File | What it is |
|---|---|
| `index.html` | The three personas and where each journey starts. |
| `executive.html` | Two minutes before the first meeting: Today → the briefing → the top paper. |
| `analyst.html` | Ten-minute triage: the corpus, search, screening filters, sort, the screening log, a second look. |
| `expert.html` | A protected hour with one paper: the scorecard, the evidence, asking the full text. |
| `journeys.json` | Source of truth for the steps: each step's caption (sees / does / decides), the actions the capture script performs, the evidence paths and the verifier's verdict per journey. The caveat boxes on the pages are hand-written from the verifier's notes and are not regenerated. |
| `shots/<journey>/` | Stills (`NN-<slug>.png`), clips (`NN-<slug>.mp4` + poster) and a `manifest.json` per journey. |

Personas are the ones in `frontend/PRODUCT.md`. The pages stay at the UX layer
on purpose: what the person sees, does and decides on each screen. Nothing
about routes, endpoints or components.

## How the evidence was captured

`frontend/scripts/journeys.ts` (`bun run journeys`) drives one real browser
session per journey at desktop 1440×900, English UI, against a local Next
server pointed at the **prod-snapshot replay** (`local-data/sri-prod-2026-09-01`,
Hybrid Computing workspace). It records the session as video, takes a still
after each step, and cuts the clips for steps marked `clip: true`. The one
step the replay cannot serve, the streamed answer in the expert journey, was
captured on the live system because the replay rejects writes.

Every journey was then replayed independently with `agent-browser` by a
separate verifier, which asserted each step's expected on-screen strings,
inspected every still and clip, and recorded its verdict in `journeys.json`.

Two pieces of evidence were edited after capture, both recorded in the
journey's `verified.notes` and the manifest: the expert step 6 clip lost its
first second (the live system lands on an internal test workspace before the
Hybrid Computing pin applies), and its still, poster and clip were cropped to
1112 px wide to leave out the conversation history rail, which on the live
system holds unrelated threads.

## Regenerate

```bash
cd frontend
bun run snapshot:serve                                     # replay on :8010 (see local-docs/snapshot-replay.md)
BUILD_DIR=.next-agent9 PORT=3009 SITE_URL=http://localhost:3009 BACKEND_INTERNAL_URL=http://localhost:8010 bun run dev
bun run journeys --journey executive                       # or analyst / expert
git checkout -- tsconfig.json                              # Next rewrites it
```

For the production step export `SCREENSHOT_PASSWORD` in the shell first
(never on a visible command line). See the header of `scripts/journeys.ts`
for the full CLI.
