# Design system

Research Intelligence's look is the **Souverän** brand direction (direction K from
`docs/brand-directions.html`, weiss surface, designer-adjusted): a sovereign,
security-operations register — warm-neutral surfaces on a cool gray page, hairline
rules, a letterspaced-caps wordmark, mono figures that keep every score
audit-grade, and a small accent square marking each section like a status light.
One cold turquoise signal does all the pointing. Nothing decorative — every color
and weight earns its place. The audience includes non-technical executives, so the
bar is "immediately legible," not "impressive."

## Type

- **UI sans:** Switzer (loaded in `layout.tsx`), falling back to `system-ui`.
  Stand-in for the direction's intended Söhne / Neue Haas Grotesk.
- **Figures:** IBM Plex Mono (loaded in `layout.tsx`, wired to `--font-mono`).
  Scores, deltas, and metrics are set `font-mono tabular-nums` so columns and
  rings align, don't jitter, and read as instrument output.
- **Serif:** used _only_ where long-form reading is the point — the Reading Room
  and the Morning Briefing. Tailwind's default `font-serif` stack.
- **Wordmark:** letterspaced caps — `uppercase tracking-[0.14em] font-semibold`
  (`ScannerWordmark`). Differentiates the brand from every other type treatment.
- **Section labels:** `text-xs font-semibold uppercase tracking-[0.18em]` in ink,
  preceded by a 6×6px accent square. The `SectionLabel` component enforces this;
  `PageHeader` eyebrows get the same square in muted ink.

## Color

Tokens live in `src/styles/tailwind.css` (`:root` = weiss, `.dark` = schwarz —
no toggle is wired; the app renders weiss). The zinc/gray/blue/amber/green/red
Tailwind scales are **remapped** there to Souverän values, so legacy utility
classes stay on-brand; new code should prefer the semantic utilities.

| Job                     | Token / value                                       |
| ----------------------- | --------------------------------------------------- |
| Page background         | `bg-background` `#F3F4F4`                           |
| Card surface            | `bg-surface` `#FFFFFF`                              |
| Ink                     | `text-foreground` `#131311`                         |
| Muted ink               | `text-muted-foreground` `#6D6D65`                   |
| Hairline border         | `border-line` `#DEDED7`                             |
| Soft hairline (in-card) | `border-line-soft` `#EBEBE4`                        |
| Signal / links / "hot"  | `accent` `#00C3CD` (text on light: blue-700 `#00767E`) |
| Positive delta          | `text-positive` `#1E7B44`                           |
| Negative delta          | `text-negative` `#B5402C`                           |
| Concept marker / warn   | `bg-warn` `#E3C230` (Zitrus; text: `text-warn-ink` `#7D6510`) |
| Primary action          | foreground (near-black, inverts in dark)            |
| Tile wash               | `bg-foreground/3` (3% ink over the surface)         |

Raw `#00C3CD` fails contrast as body text on white — use `text-blue-700`
(`#00767E`) for accent-colored text; Zitrus text always via `text-warn-ink`.

### Charts

Chart color follows the **validated dataviz palette** (`components/charts.tsx`),
not ad-hoc hues:

- **Categorical** — the eight sectors each own a fixed slot from the CVD-safe
  categorical order (`src/data/sectors.ts`); the signal slot is the accent family
  (`#0097A3`), the compute slot is Zitrus. Color follows the _sector_, never its
  rank in a given chart.
- **Sequential** — the accent ramp (`seqBlue`, now `#E9F8F9 → #00434C`) for
  magnitude (the Matrix heatmap). Light → dark, single hue, never a rainbow.
- **Score rings** — a small semantic scale: accent ≥ 75 (strong signal), Zitrus
  ≥ 55 (worth a look), neutral below (background). Butt-capped strokes.
- **Meters** — 3px tall, squared (no rounding), `line-soft` track, accent fill.
- **Chrome** — axes, gridlines, and labels use zinc utility classes (remapped to
  the warm-neutral ramp) with `dark:` variants so they adapt to theme.

> **Honest caveat:** the app ships without a theme toggle, so it renders weiss by
> default. Marks are tuned for the light surface. The `.dark` block already holds
> the schwarz tokens if a toggle is added; categorical marks should then switch
> to the palette's dark steps.

Charts are dependency-free inline SVG — no charting library. Primitives:
`Sparkline`, `ScoreMeter`, `RadarChart`, `QuadrantChart`, `HeatGrid`, plus the
`SignalScore` ring in `scanner-ui.tsx`.

## Layout patterns

- **Sidebar shell** — core nav (Dashboard, Papers, Trends, Watchlist, Tuning) at
  the top; a **Concepts** section below it listing all concept pages; Settings and
  a Signal Stream shortcut pinned at the bottom. The concept list is generated from
  `src/lib/concepts.ts` so sidebar and index never drift. The current-item
  indicator is an accent bar.
- **Page header** — `PageHeader` gives every page a squared eyebrow, a title, a
  one-line description, and an optional action slot. Consistency here is what makes
  a ten-page app feel like one product.
- **Cards** — `Card` is the single surface primitive: 2px radius, `line` hairline
  border, the Souverän `shadow-xs`, white surface on the gray page. Stat tiles use
  the 3% ink wash (`bg-foreground/3`) with `line-soft` borders so they read as
  distinct areas without harsh division.
- **Callouts** — `Tldr` in `scanner-ui.tsx`: accent-tinted panel
  (`border-accent/40 bg-accent/6`) with a mono letterspaced label.
- **Detail pages** are max-width-constrained and center-aligned for readability;
  index/browser pages go full width.
- **Score-first** — wherever a paper appears, its Signal Score ring leads, then
  sector, then title, then the model's one-liner. The hierarchy is deliberate:
  score → context → claim.

## Components map

| File                        | Holds                                                                            |
| --------------------------- | -------------------------------------------------------------------------------- |
| `components/brand.tsx`      | `ScannerMark` (aperture logo), `ScannerWordmark` (letterspaced caps)             |
| `components/charts.tsx`     | inline-SVG chart primitives + palette                                            |
| `components/scanner-ui.tsx` | `PageHeader`, `Card`, `StatTile`, `SignalScore`, `ScoreRow`, `Tldr`, badges, chips |
| `components/paper-card.tsx` | the standard paper list row                                                      |
| `components/answer-markdown.tsx` | `AnswerMarkdown` — model-written markdown in app tokens; mono figures; streaming caret; `[Page N, …]` markers as citation chips (opt-in via `citations`) |
| `components/skeleton.tsx`   | `Bone.*` placeholder primitives + `Skeleton.Region` — see `docs/skeletons.md` |
| `components/*` (Catalyst)   | retained UI primitives: `sidebar`, `dropdown`, `avatar`, `button`, `input`, etc. |

The old Tailwind Plus _marketing_ components (bento cards, testimonials, logo
clouds, gradients) were deleted — they have no place in an internal tool.

## Voice

Plain, confident, not preachy. The client knows what the product does, so copy
states findings ("The data wall may be cracking — quietly, and with caveats") and
avoids marketing verbs. Rationales read like an analyst's margin note, not a
model's hedge.
