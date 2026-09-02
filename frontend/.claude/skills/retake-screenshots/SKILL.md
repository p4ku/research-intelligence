---
name: retake-screenshots
description: Retake the demo screenshots from rs.adder.dev and rebuild the overview PDF. Use after design tweaks, when screenshots look stale, or when the user asks to refresh the screenshots or the design/overview paper.
---

# Retake screenshots and rebuild the overview paper

## 1. Capture from production

Run the capture script against production — never against a local dev server
(dev shots can carry the Next.js dev-indicator badge and stale UI):

```sh
scripts/screenshot-pages.sh https://rs.adder.dev
```

Run it in the background (it takes several minutes: EN + DE, desktop + mobile,
core pages, roadmap/concept pages, and the pinned detail views including the
outreach drawer). Then check the log for `error`, `retrying`, or `giving up`
lines — a run can "succeed" while individual pages failed.

The script logs in itself (credentials are in the script) and overwrites
`screenshots/<lang>/{core-preview,core-mobile,roadmap}/` in place.

## 2. Verify against the paper

The file to check is `docs/research-scanner-overview.tex`. Every `\shot{...}`
and `\detailshot{...}` argument resolves to `screenshots/en/<arg>.png`
(see `\graphicspath`). Confirm each referenced PNG exists and has a fresh
mtime — a `.tex` reference with no matching file means the script's pinned
IDs (paper/trend/author/packet, defined at the top of
`scripts/screenshot-pages.sh`) have drifted from the demo data.

## 3. Inspect the images with Opus subagents

Do not eyeball dozens of PNGs in the main context. Fan out `model: opus`
subagents (per the project's compute preference) to Read the screenshots and
report back, checking each image for:

- the Next.js dev badge (dark circled "N", bottom-right) — means a dev-server
  capture; recapture from production
- error states: 404 text, error overlays, empty/blank content areas
- stale UI: sidebar labels, section names, or copy that contradicts the
  current design (compare against a freshly captured known-good shot)

Batch ~5–10 images per subagent and have them return a per-image verdict.

## 4. Rebuild the PDF

```sh
tectonic docs/research-scanner-overview.tex
```

This writes `docs/research-scanner-overview.pdf` in place. Fix any missing-
graphic errors (they name the exact `.png` the `.tex` expects), then rebuild.

## Notes

- Wording: the future-phase concepts are _possibilities under consideration
  for future phases_ — never describe them as "on the roadmap".
- The screenshot gallery (`screenshots/index.html`) is built separately by
  `scripts/build-screenshot-gallery.ts`; regenerate it too if it's in use.
