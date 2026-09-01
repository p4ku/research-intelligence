# Skeletons and streaming

Every data route in this app is `force-dynamic`. Before this work, each one
awaited all of its data in a single `Promise.all` and returned nothing until the
slowest call landed, so a navigation froze on the previous page. The fix is not a
skeleton component — it is **boundaries**: each section awaits only what it
renders, and shows a placeholder shaped like the thing that is coming.

Pass 1 (the dashboard) is done and establishes the conventions below. Passes 2
and 3 are the same recipe applied to the remaining shapes; they are listed at the
bottom with the specifics you need.

## The four rules

**1. Scan sweep, never `animate-pulse`.** `animate-pulse` already means "this run
or step is executing" (`studio/run-presentation.tsx`, `studio/runs/[id]/step-timeline.tsx`)
and the streaming caret in `answer-markdown.tsx`. Reusing it for loading would
conflate two meanings. The sweep is a single `[data-skeleton]::after` gradient
per region in `styles/tailwind.css`, driven by an animated `@property --bone-x`
so the region needs no `overflow: hidden` — card rings and shadows inside stay
intact. One animation per region, however many bones it holds.

**2. `FooSkeleton`, never `Foo.Skeleton`.** Dotting into a `'use client'` module
from a Server Component throws _"Cannot access X on the server."_ `paper-card.tsx`
and `run-papers.tsx` are client modules and `page.tsx` / `loading.tsx` are not, so
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
   inherits type from its slot; `Bone.Number` reserves `N ch` of the mono face —
   put it inside something carrying `font-mono`. Percentage widths only in block
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
bun run screenshots --routes skeletons      # the gallery, sweep frozen, in the usual review loop
bun test                                    # incl. the loading-convention ratchet
```

`--stream` compares byte positions, not arrival times: a fast local server
delivers several boundaries in one chunk. To sanity-check that the assertion is
real, point it at a route with no boundaries (`--stream /papers`) and watch it
fail.

The gallery accepts `?motion=static` to freeze the sweep; `prefers-reduced-motion`
removes it and reduces the handoff to an instant swap.

## Done (pass 1)

`components/skeleton.tsx` (the primitives), the sweep and handoff CSS,
`PaperCard`, `StatBand` / `StatTile`, `AnswerMarkdown`, `RunPapers`, and the
dashboard streaming in three sections.

## Pass 2 — the Studio surfaces

Highest value per unit of work; both shapes are extremely regular.

| Shape         | File                                                         | Skeleton                                                                                                                                                                              |
| ------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Runs table    | `app/studio/runs/page.tsx` (rows via `components/table.tsx`) | Row frame with a `Bone.Number` per tabular column (short id, duration, counts, cost) and a `Bone.Chip` for the status pill. 8 rows. The band above it already has `StatBandSkeleton`. |
| Step timeline | `app/studio/runs/[id]/step-timeline.tsx`                     | Rail `Bone.Dot` + connector, title line with 2–3 chips, a summary line, and the right rail: a 96px duration bar (`Bone.Block h-1 w-24`) over three mono lines.                        |

Watch for: the timeline's running-step dot is `animate-pulse` **status**, not a
bone — leave it alone. Both routes then get a `loading.tsx` and come off
`KNOWN_UNCOVERED`. The Studio is English-only, so no locale keys are needed.

## Pass 3 — paper detail and the ask rails

| Shape           | File                                                      | Skeleton                                                                                                                                                                                                           |
| --------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Signal ledger   | `components/signal-ledger.tsx`                            | 34px mono score (`Bone.Number`), segmented bar as a `Bone.Block`, three labelled slider rows. It animates the score with `useMotionValue`/`useSpring` — the skeleton must not, or the spring will fight the sweep. |
| Score variables | `components/score-variables.tsx`                          | Scalar grid / variable list; rows are uniform.                                                                                                                                                                     |
| Charts          | `components/charts.tsx`                                   | `RadarChart`, `QuadrantChart`, `HeatGrid`, `ScoreMeter`, `Sparkline` have fixed viewBoxes, so an exact-size `Bone.Block` lands the chart with no shift.                                                            |
| Ask rails       | `app/(sidebar)/ask/history-rail.tsx`, `paper-palette.tsx` | Session rows (title + timestamp); palette rows (title, author, source, score).                                                                                                                                     |

`papers/[id]` and `ask` load their whole corpus server-side and hand it to a
client browser component, so they want one whole-list skeleton rather than
per-row streaming.

## Later, not now

`cacheComponents` (Partial Prerendering) would make each route's shell static, so
the skeletons ship with the HTML and the server does no work before first paint.
It is a `next.config` change plus an audit of every layout that reads runtime
data, which is why it is not part of this work. Note that `(sidebar)/layout.tsx`
awaits the session and the workspace list, so on a **hard** load `loading.tsx`
cannot appear until those resolve; on client navigation within the group it is
instant. PPR is what would fix the hard-load case.

Per-section error boundaries are also still missing: a failure in any section
still replaces the whole page via `(sidebar)/error.tsx`.
