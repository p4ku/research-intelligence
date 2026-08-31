# Product

## Register

product

## Users

Three personas inside Schwarz Group (Lidl, Kaufland, PreZero, STACKIT), per `docs/design.md` and `docs/concepts.md`:

- **Executive** — wants a two-minute morning briefing; will never open a filter.
- **Analyst** — lives in the filters, triages the feed daily, edits the weekly digest.
- **Domain expert / deep-diver** — wants a protected hour with one paper.

A recurring fourth: a core-disruption-team member who hands one signal per week to another Schwarz business unit.

## Product Purpose

Research Intelligence reads new research papers (starting with the agents & AI corpus) continuously, scores each on six dimensions (TRL, Novelty, Significance, Momentum, Rigour, Commercial) rolled into a headline Signal Score with plain-English rationales, and surfaces "the next big thing" before competitors see it. Success: a breakthrough is caught while it is still quiet, and a non-technical reader understands why it ranked where it did.

## Brand Personality

Restrained, professional, immediately legible. Plain, confident, non-marketing voice — states findings with caveats rather than selling. Honest about uncertainty: misses are shown at equal weight to hits. Nothing in a briefing is invented.

## Anti-references

- "Impressive" over legible — decorative dashboards, animated hero metrics, gradient-heavy AI-tool aesthetics.
- Startup-landing-page energy; this is an internal enterprise instrument for a German corporate audience.
- Consumer news-app styling that undermines the audited-number credibility of the scores.

## Design Principles

- Score-first hierarchy: Signal Score → sector → title → one-liner, in that visual order.
- One semantic accent per job (signal, positive, negative); tabular numerals on anything scored.
- Every score ships with its rationale — the design must always leave room for the "why".
- Immediately legible to a non-technical executive; density is earned, never default.
- The lightest separation that works: whitespace, then hairlines, then cards.

## Accessibility & Inclusion

- Categorical (sector) palette is fixed-slot and CVD-safe with light + dark steps per hue (`src/data/sectors.ts`).
- Body text contrast ≥ 4.5:1; scores never encoded by color alone (always numeric).
- Dark styles fully authored across the app (awaiting a toggle); marks tuned per surface.
