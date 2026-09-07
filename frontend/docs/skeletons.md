# Skeletons and streaming

Every data route in this app is `force-dynamic`. Before this work, each one
awaited all of its data in a single `Promise.all` and returned nothing until the
slowest call landed, so a navigation froze on the previous page. The fix is not a
skeleton component — it is **boundaries**: each section awaits only what it
renders, and shows a placeholder shaped like the thing that is coming.

Pass 1 (the dashboard) established the conventions below; passes 2 (Studio) and
3 (paper detail, the assistant, the briefings) applied the same recipe. What is
covered, what was learned, and the short debt list are at the bottom.

## The four rules

**1. Scan sweep, never `animate-pulse`.** `animate-pulse` already means "this run
or step is executing" (`(sidebar)/runs/run-presentation.tsx`, `(sidebar)/runs/[id]/step-timeline.tsx`)
and the streaming caret in `answer-markdown.tsx`. Reusing it for loading would
conflate two meanings. The sweep is a single `[data-skeleton]::after` gradient
per region in `styles/tailwind.css`, driven by an animated `@property --bone-x`
so the region needs no `overflow: hidden` — card rings and shadows inside stay
intact. One animation per region, however many bones it holds.

**2. `FooSkeleton`, never `Foo.Skeleton`.** Dotting into a `'use client'` module
from a Server Component throws _"Cannot access X on the server."_ `paper-card.tsx`
and `dashboard/ledger.tsx` are client modules and `page.tsx` / `loading.tsx` are not, so
the skeleton is always a separate named export, co-located in the component's own
file. (`Bone` and `Skeleton` keep the dotted form only because
`components/skeleton.tsx` carries no directive.)

**3. `ViewTransition` only in `page.tsx` / `loading.tsx`.** Next 16 bundles a
React canary that exports it, but `bun test` resolves the top-level `react`,
which does not — importing it in a component file breaks the test run. Types come
from `src/types/react-canary.d.ts`; there is no `next.config` flag to set. Do not
convert that file to `import 'react/canary'`: `verbatimModuleSyntax` would emit a
runtime import of a module that does not exist.

**4. Skeletons are for the first paint only.** Sort, filter and paginate run
inside `startTransition` and dim the stale list (`data-pending` →
`opacity-60`); the old data beats no data. Never put a skeleton over streaming
chat — `ScanningLine` and the caret are already a better loading state. The
dashboard _brief_ is the exception that proves it: a finished document, not a
live one.

## Adding a skeleton

1. **Split the component into a frame.** `FooFrame` takes slots and owns every
   layout and type class; `Foo` fills the slots with data, `FooSkeleton` fills
   them with bones. One set of classes means the two cannot drift. Mark the frame
   root `data-shape="foo"` + `data-state="loaded|skeleton"` and each measurable
   row `data-row="…"`.
2. **Size bones honestly.** `Bone.Text` occupies exactly `1lh` per line and
   inherits type from its slot; `Bone.Number` reserves `N ch` of the inherited
   font, which is exact for digits in a `font-mono` slot or a `tabular-nums`
   sans cell (a `ch` is a digit's width). Percentage widths only in block
   context: in a flex row a `%` width on a shrink-to-fit item resolves to 0, so
   use `ch` or `Bone.Chip` there. Line widths come from a fixed pattern, never
   random, so screenshots and drift runs stay stable.
3. **Wrap the section, not the component.** One `Skeleton.Region` per Suspense
   fallback carries `aria-busy`, a single `sr-only` status, and hides bones from
   assistive tech. Component skeletons render bones only. `status` must be an
   already-translated sentence — `skeleton.tsx` is shared and cannot call `useT`.
4. **Add the pair to `/studio/skeletons`** so the drift check covers it.
5. **Give the route a `loading.tsx`** composed from the same section skeletons the
   page uses as fallbacks, and remove the route from `KNOWN_UNCOVERED` in
   `src/app/loading-convention.test.ts`. That list may only shrink.

## Verifying

Needs a running app (see `local-docs/snapshot-replay.md` for the replay stack).

```bash
bun run skeleton:drift                      # loaded vs skeleton geometry, desktop gates at 4px
bun run skeleton:drift --stream /dashboard  # fallback must precede the first boundary completion
bun run skeleton:drift --not-found /papers/00000000-0000-4000-8000-0000000000ff  # see pass 2 notes
bun run screenshots --routes skeletons      # the gallery, sweep frozen, in the usual review loop
bun test                                    # incl. the loading-convention ratchet
```

`--stream` compares byte positions, not arrival times: a fast local server
delivers several boundaries in one chunk. To sanity-check that the assertion is
real, point it at a route with no boundaries (`--stream /settings`) and watch it
fail. Run the drift and stream checks cookieless: with a demo flag off (say
`all_papers`), the hidden route renders the not-found card with no boundaries
of its own, so a control against it fails for the wrong reason and reads
exactly like the assertion working.

The gallery accepts `?motion=static` to freeze the sweep; `prefers-reduced-motion`
removes it and reduces the handoff to an instant swap.

## Done (pass 1)

`components/skeleton.tsx` (the primitives), the sweep and handoff CSS,
`PaperCard`, `StatBand` / `StatTile`, `AnswerMarkdown`, `RunPapers`, and the
dashboard streaming in three sections.

## Done (pass 2) — the Studio surfaces

`/runs` streams band + filter strip + table behind one boundary (they
all read the one list): `runs/runs-table.tsx` (`RunsTable` / `RunsTableSkeleton`
over a frame that also owns the column list), `runs/run-tabs.tsx`,
`runs/sections.tsx`, `runs/skeletons.tsx`, `runs/loading.tsx`.

`/runs/[id]` streams two sections — the head (header, band, facts) on
the run record and the steps on the component-run list: `[id]/run-facts.tsx`,
`[id]/step-timeline.tsx` (`StepTimelineFrame` takes the rail dot's colour as a
slot, so the running step's `animate-pulse` stays with the loaded list),
`[id]/sections.tsx`, `[id]/skeletons.tsx`, `[id]/loading.tsx`. The failed-steps
notice moved from above the band to directly above the Steps section, where the
steps it names are. `StepSummarySkeleton` lives with `StepSummary` in
`(sidebar)/runs/run-presentation.tsx`.

Fixtures for the gallery: `lib/bff/pipeline-runs/fixtures.ts` and
`lib/bff/component-runs/fixtures.ts`, schema-checked by `lib/bff/fixtures.test.ts`.
The six-step fixture _is_ the timeline skeleton's drift contract: spend and
model lines on the LLM steps only.

Things learned:

- **Tables: mark the headers, not the cells.** Column widths are content-derived
  under `whitespace-nowrap`, so each `<th>` carries `data-row="col"` and the
  drift check catches a bone that pushes a column wider. A bone narrower than
  its header adds nothing to the column, which is the easy way to make
  header-dominated columns match exactly.
- **A `ch` is a digit; prose is ~15% narrower.** Size prose bones in fractional
  `ch` (`'15ch'` for an 18-character label) or let the drift run tell you.
- **`StatBandSkeleton subs` takes `null`** for a cell that has no sub line in
  the loaded band, `undefined` for a bone.
- **`PageHeader` title/description and `Breadcrumbs` labels are nodes** so a
  `loading.tsx`, which gets no params, can bone the run id.
- **A `loading.tsx` on a dynamic segment changes the not-found status.** Next
  wraps the page in the loading boundary, so a dead `/runs/<id>` now
  streams the shell with HTTP 200 and renders `(sidebar)/not-found.tsx` in-stream
  with `noindex`. Accepted for this route (behind auth; the not-found page still
  shows), decided 2026-09-02. Any route that must keep a genuine 404 must call
  `notFound()` in a layout above the loading boundary, or skip `loading.tsx`.

## Done (pass 3) — paper detail, the assistant, the briefings

`/papers/[id]` streams the whole record — the nav row, header, screening,
assessment rows, abstract, provenance, the score rail, and the chat pill —
behind **one** boundary, because everything reads the one `papers.get` (now
React-cached, so the title crumb, `generateMetadata` and the record share the
call; the nav row's neighbours come from the cached `papers.listAll`). Both go
when the `all_papers` demo flag is off — no crumb trail, and `PaperNav` keeps
its (redirected) back link but withholds the pager, so `neighboursOf` is never
called; the skeletons take the same `features` prop and make the same call, or
the shell paints a crumb bar that then vanishes. Files:
`papers/[id]/paper-header.tsx`, `paper-nav.tsx`, `assessment-rows.tsx`,
`score-rail.tsx`, `sections.tsx`, `skeletons.tsx`, `loading.tsx`;
`PaperChatFrame` / `PaperChatSkeleton` in `paper-chat.tsx` (the pill and the
sheet it opens). Since the sidecar layout (7 Sep 2026) the rail reserves five
bars and a radar and the assessment five rows — production's shape; a domain
with fewer numeric dimensions sees both shorten on load. It has a
`loading.tsx`, so a dead paper permalink now answers HTTP 200 with the
not-found page in-stream — the same trade as the run page, decided 2026-09-02
and pinned by `skeleton:drift --not-found`.

`/ask` streams the canvas behind one boundary (the corpus feeds the picker,
the sessions feed the recent-chats sidecar; both block it). The canvas's
chrome lives in `ask/console-frame.tsx` (no directive, no hooks) so
`loading.tsx` renders the real top bar, greeting and composer box with a bone
only where the typed question would go. Neither the picker nor the sidecar is
on screen until the reader asks for them, so neither is boned here;
`HistorySidecarSkeleton` and `PaperPickerSkeleton` exist for the gallery.
`ask/sections.tsx`, `ask/skeletons.tsx`, `ask/loading.tsx`.

`/briefing` streams the reading room behind one boundary
(`briefing/edition-browser.tsx` is now a frame with `EditionBrowserSkeleton`);
`/briefing/[date]` streams the head (crumbs, title, funnel, brief) and the
papers separately, one fetch each; `/briefing/[date]/run` streams the funnel
and the new `exclusions-table.tsx`. Each has `sections.tsx`, `skeletons.tsx`,
`loading.tsx`. The date pages validate the param's shape before the shell goes
out (`isEditionDate`), so a malformed date is still a plain 404.

Things learned:

- **One fetch, one boundary.** Splitting the paper page per card would have
  streamed nothing separately; the split follows the data, not the layout.
- **Reserve the shape production takes.** The paper skeleton reserves five
  assessment rows and five rail bars with a radar because that is what the
  production domains score; the stub fixture has three dimensions, so stub
  mode and the screenshot stack see the record shorten on load, and the
  gallery pairs are built from the fixture's own length.
- **Some things get no skeleton.** A component that renders `null` in
  several branches (the old score-variables card did) must not get a bone
  that reserves space where nothing renders — a guaranteed drift finding.
  `Sparkline` was already covered by `StatBandSkeleton`; `RadarChart` at a
  literal `size` is an exact `Bone.Block`. `ScoreMeter`, `QuadrantChart` and
  `HeatGrid` have no call sites.
- **A skeleton for the first paint only, even for a popover.** The paper
  picker is client state and never blocks paint, so `PaperPickerSkeleton`
  exists for `loading.tsx` and the gallery (`placement="static"` puts it in
  flow so the drift check can measure rows); the live picker is never replaced.
- **Refs and motion stay in the client file.** `ask.tsx` keeps `bodyRef`,
  `dockRef`, the `motion.div`s and the textarea; the frame module exports the
  class constants those elements use, so the skeleton still shares every class.
- **A region that must fill its parent** takes `innerClassName` — the console
  is a fixed-height flex column and the bones inside have to inherit it.
- **The gallery page is a Server Component**, so loaded panes for components
  that take callbacks (`HistorySidecar`, `PaperPicker`) come from a `'use client'`
  demo wrapper (`studio/skeletons/gallery-clients.tsx`).
- **Per-request `cache()` on the services** (`papers.get`, `papers.listAll`,
  `briefings.listAll`, `briefings.getByDate`) is what makes sibling sections
  cheap; without it, `source=django` would fetch once per section.
- **The raw corpus is held across requests** (`lib/bff/corpus/snapshot.ts`):
  one snapshot of workspaces + papers + extractions per signed-in user,
  revalidated against the run ledger's fingerprint rather than a clock.
  Pages never fetch the corpus themselves — they read the services, which
  read the snapshot — so a warm navigation costs Django nothing and the
  skeleton is on screen for the Next round trip only.

## Done (pass 4) — Home (7 Sep 2026)

Home was rebuilt around the MVP spec (search, the Current briefing as a
masthead, Recent Briefings beside Start New Briefing). Two boundaries:
`MastheadSection` and `LedgerSection` (the ledger and the form share one,
because the form's disabled state depends on the same run list). Pairs
`home-masthead`, `home-ledger` and `home-run-card` in the gallery; the
`run-papers` pair went with the old page. The ledger's expanded row
(`data-row="brief"`) has no skeleton — it only opens on a click.

## Done (pass 5) — Briefings archive (7 Sep 2026)

`/briefing` became the spec's ledger (domain, period, generated, screened,
included; Current highlighted; domain chips, star, twenty a page), one
boundary around `LedgerSection`; pair `briefing-ledger`. The reading room it
replaced moved to `/briefing-archive` unchanged and keeps the
`edition-browser` pair. As on Home, the expanded row (`data-row="brief"`)
has no skeleton. The page's fallback knows the domain names (the chip row
is real); `loading.tsx` bones them.

## Later, not now

Still on `KNOWN_UNCOVERED`: `/settings` (two forms, mostly static chrome; also
the `--stream` negative control above) and `/tuning` (one fetch; an
`InfluenceBar` bone would do it). `/papers` is flag-gated: with `all_papers`
off its `loading.tsx` returns null and the route streams the not-found card
inside an HTTP 200, the same shape `/ask` gives.

`cacheComponents` (Partial Prerendering) would make each route's shell static, so
the skeletons ship with the HTML and the server does no work before first paint.
It is a `next.config` change plus an audit of every layout that reads runtime
data, which is why it is not part of this work. `(sidebar)/layout.tsx` now reads
only cookies (session, language) — each page fetches the domain list itself —
so on a **hard** load `loading.tsx` appears as soon as the shell streams; on
client navigation within the group it is instant. PPR is what would make the
shell itself static.

Per-section error boundaries are also still missing: a failure in any section
still replaces the whole page via `(sidebar)/error.tsx`.
