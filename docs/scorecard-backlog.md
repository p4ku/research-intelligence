# Scorecard backlog (after PR #126)

**This file is the live to-do list** for the scorecard and editions move that
PR #126 merged on 9 Sep 2026 (`main @ 7832f98`). The PR moved paper-scorecard
assembly from the Next.js BFF into Django (`/api/workspaces/{id}/scorecard/`,
`/api/papers/{id}/scorecard/`, `/api/workspaces/{id}/editions/`) and flipped
the BFF's `papers` and `briefings` sources to `django` by default. The service
is the right direction; these are the things the audit found that still need
attention, ranked by what to do next.

Evidence: the branch was run against the 8 Sep 2026 prod snapshot (1,979
papers, 413 extractions, 23 runs) loaded into a scratch Django. Numbers below
come from that. The audit page with screenshots and tables is
`pr-126-audit.html` in the audit session's scratchpad; the loader and
measurement scripts (`load_snapshot.py`, `measure.py`, `bff_timing.py`) sit
beside it. To reproduce: migrate a fresh SQLite Django in a worktree, run the
loader, serve on `:8027`, run the app with
`BACKEND_INTERNAL_URL=http://localhost:8027`. The snapshot replay server cannot
serve this code path (it never captured `/scorecard/` or `/editions/`).

Sizes: S = under an hour, M = half a day, L = a day or more. "Live" means
users see it on prod now; "latent" means it needs a trigger.

GitHub issues filed on 9 Sep 2026 for the same findings, so PRs can close
them: item 1 → #128 · item 2 → #129 · item 3 → #127 (and the older #120) ·
item 6 → #134 · item 7 → #130 and #134 · items 10, 15, 16 → #132 · item 12
→ #131 · item 17 → #133 · item 18 → #135. Items 4, 5, 8, 9, 11, 13, 14, 19
and 20 have no issue yet; cite this file.

---

## P0 — prod is degraded until these land

### 1. Every page view drains the whole workspace scorecard, uncached — live, M, frontend
`papers.listAll` calls `/api/workspaces/{id}/scorecard/` with no page size;
`listEverywhere` drains 200 a page for every membership; nothing is held
across requests (`src/lib/bff/papers/service.ts:88-119`). The per-user corpus
snapshot in `src/lib/bff/corpus/snapshot.ts` and its `trustCorpusFor` window
are bypassed. Callers: `/papers`, the Ask palette, Home search, the paper
pager (`papers/[id]/sections.tsx:171`), `/bff/status`, the scoring page.
- Full drain on the snapshot: 91.5 MB of JSON (the old cached corpus was
  22.7 MB); 39.7 MB and 33.7 MB for the two largest domains.
- A 20-row Papers page ships 2.5 MB; palette and search keystrokes take
  about 2 s each on a local SQLite backend.
- Fix: a second store next to `corpusStore` holding `ScoredPaper[]` per
  workspace, keyed on the run-ledger version, same TTL, byte budget and
  trust window, filled through `drain()` + `djangoPage()` at 200 a page.
  `listAll`/`listEverywhere`/`corpusTruncated` read it; `listRun` stays live
  and run-scoped. Read `results` with a `papers` fallback so item 7 can drop
  the duplicate key.

### 2. Calibration domains are visible everywhere — live, S, frontend
`src/lib/bff/workspaces/visible.ts` and its test were deleted; issue #101's
`is_calibration` flag does not exist on the backend. `workspaces.listAll`
feeds the domain switcher, Home's start box, the Papers facets, the palette,
search, the briefing ledger and Home's recent briefings.
- Fix: restore `visible.ts`, the filter in `workspaces/service.ts` and the
  README paragraph from `main @ ff7460b`, until the backend flag ships.

### 3. The editions list keeps one run per day — live, S backend + S frontend
`api/views/workspaces.py:322-329` dedupes by day. Hybrid Computing OLD: 16
completed runs become 8 editions; runs with 29, 27, 26, 7, 3 and 2 papers
vanish from Home and the archive; four zero-paper runs come back. Undoes
PRs #85, #117, #123 and #124. `edition_detail?run_id=` works but echoes the
URL date instead of the run's. The brief is the pipeline's status message
("Full SLR pipeline finished successfully. Papers: 128 fetched…") and the
title is English in the German UI.
- Backend: one result per completed run, `date` from the run in both views;
  update `test_editions_list_field_pruning_and_deduplication`, add a
  same-day pair test.
- Frontend: the `django` branches of `briefings.listAll`/`getByDate` run
  `templateProse` (`briefings/prose.ts`) with `lang` over the edition's
  funnel and papers, as `compose.ts` does.

### 4. A display key changes signal scores — latent, S, backend
`Extraction.exit_metric` now returns `primary_frontend_metric` before the
configured exit metric (`models/extraction.py:558-571`); the scorer
(`scorer.py:138`), the digest, the narrative report and the admin all read
that property. Probe: a score of 75 became 2019.0 (the first number in the
insight prose); a TRL definition pointed at `trl_label` made `trl_level` a
string. Nothing on prod sets the field yet.
- Fix: delete the step; the scorecard code reads the field directly. Test
  that setting the field leaves `exit_metric` and `extract_paper_parameters`
  unchanged.

### 5. Reading a definition and saving it back flips its headline — latent, M, backend
Representations emit the fallback secondaries (`exit_metrics[1:]`) from
`get_secondary_frontend_metrics_list` (`serializers/workspaces.py:49-50`,
`workspace_service.py:188-189`, MCP list/get). A client that echoes the GET
body persists them, switching the definition into explicit mode and skipping
the postprocessing rule. Probe: headline 88.5 became 75.
- Fix: a raw accessor for representations; keep the fallback inside the
  scorecard path only. Test the GET→PUT round trip.

## P1 — correctness and payload

### 6. Ordering by score multiplies rows and drops papers — latent, M, backend
`?ordering=-signal_score` orders by the multi-valued metrics join
(`scorecard_service.py:706-731`). Hybrid Computing OLD: `count` 152, 752
rows, 85 MB; with `page_size=200` a page holds 40 distinct papers and
`next: null`. The BFF does not send `ordering` today.
- Fix: annotate a `Subquery` of the target run's (or latest) metric score and
  order by it; carry `ordering`/`search`/`screening_status` in `next`/
  `previous`; test `count == len(results)` with two metrics and no run.

### 7. List payloads carry raw data twice over — live, M, backend + frontend
The workspace scorecard body holds the paper list twice (`papers` and
`results` are byte-identical). Each dimension repeats the definition's
`response_schema` (8.2 KB), `fields_data`, and the alias pairs
`primary_metric`/`main_metric`, `secondary_metrics`/`auxiliary_metrics`;
`risk_and_affiliation.raw` is the whole extraction. 960 Physical AI papers
with zero extractions each carry 15.9 KB of identical `dimensions`. The BFF
schemas gained `.passthrough()`, so all of it reaches client components and
`/bff/papers`; the detail route also forwards `definitions[].postprocessing_code`,
`extractions[]`, `metric` and the `narrative_report`.
- Backend: `build_single_scored_paper(detail=False)` for lists drops the raw
  fields; emit `results` only; keep `postprocessing_code`/`response_schema`
  out of list-level workspace summaries.
- Frontend: drop `.passthrough()` on `dimension`, `detailResponse`,
  `scorecardWorkspace` and friends; delete the raw fields from the schema
  (keep `response_schema` optional, the assessment reads titles from it);
  regenerate the contracts.

### 8. Title and abstract unescape regressed — live, S, backend (or frontend)
OpenAlex's literal backslash-n is back on the Papers list and briefing cards
("PennyLane: … hybrid quantum-classical\n computations"). PR #100's fix lives
in `src/lib/papers/map.ts:620-640`, which the Django source bypasses.
- Fix: apply the field-level rule in the backend serialiser (the backend owns
  the record), or export the helper and run it over Django-sourced papers.

### 9. Risk and Affiliation extractor ignores the spec's nesting — live, M, backend
`scorecard_extractors.py:494-628` reads top-level keys only. Prod nests
contacts, funding, codebase and dataset links and institutions under
`metadata`, and names the flag `gdpr_concern`. On the GRAINS paper the card
shows ETH Zürich only via the ecosystem match; contacts, funding and the GDPR
flag never appear, and `metadata` is dumped as a dict block reading "—".
- Fix: descend into `metadata`; aliases `gdpr_concern`, `codebase_links`,
  `dataset_links`, `institutional_affiliations`; contact dicts as
  "Name <email>". Test with the spec fixture.

### 10. Sub-measure scales and classification — live, M, backend + frontend
- TRL sub-scores get a /9 bar; dict sub-measures with no scale get /100
  (`assessment.tsx:364, 424`). Rule: a null scale is figure only.
- Definitions say `max: None`, the same paper's dimensions say 100
  (`scorecard_service.py:32` vs `:195`).
- Flat `*_score` twins re-emitted as facts; every dict secondary emitted as a
  facet and a text; the primary object's band never used; `_base_metric_key`
  folds `risk` and `risk_score`, then the frontend merges by humanised name
  so the first wins (`scorecard_extractors.py:791, 916-918`;
  `assessment.tsx:342-347`).
- The prose-vs-fact rule reintroduces the >80-character threshold the
  frontend dropped because it flipped keys between papers.
- Dict facts render as JSON text (`assessment.tsx:652`).

## P2 — product rules, i18n, hygiene

### 11. Scoring formula is back on the paper page; skeletons drift — live, S, frontend
`ScoreFormula` in `score-rail.tsx:27-64`. Rule since 7 Sep 2026: no formula,
no sliders, no score decomposition on the paper page (commit `7f2c272`).
`ScoreRailSkeleton` has no formula slot and `PaperHeaderSkeleton` no flags
card, so the loaded page is taller than its skeleton.

### 12. Blocks keyed on the definition name — latent, S, both
`Assessment` and `ScoreRail` hide any dimension whose name or key contains
"affiliation" (`assessment.tsx:674-680`, `score-rail.tsx:150-155`); a
definition named "Industry Affiliation Fit" renders "Not scored yet". The
backend sends `is_risk_and_affiliation`; filter on that only. The affix
heuristics the PR says it removed moved to Python (`\btrl\b`, "(1-10)",
`_score`/`_assessment`/`_level` regexes).

### 13. German UI shows English — live, S, frontend
"Evidence", "Sub-score", "Artifact Repository", "Funding:", "Risk Score:",
"YES/NO/None" are hardcoded (`assessment.tsx:500, 515`,
`affiliation-flags.tsx:85-89, 153, 172, 175, 185, 246`); the i18n guard only
scans `t()` literals. The edition title and brief are item 3.

### 14. Domain-less briefing permalinks render skeletal cards — live, S, frontend
`briefing/[date]/sections.tsx:265` decides "these are full records" on
`workspace_id`, which `briefings.listAll` injects into every list row, so
`/briefing/{date}?run=…` without `?domain=` renders cards from the list shape
(`dimensions: []`). Check `dimensions.length` or resolve through
`getByDate(edition.workspace_id, …)`.

### 15. Rollback path broken; mapper is dead code — latent, M, frontend
`BFF_SOURCE_PAPERS=composed` now fetches the scorecard and the old corpus
(`papers/service.ts:137-142` vs `:192-208`). The 195 new lines in
`src/lib/papers/map.ts` run only in tests and diverge from
`scorecard_extractors.py` (0–1 scale heuristic, Python-literal parsing,
insight and band aliases, dedupe suffixes). Decide: make `composed` work
again or mark it unsupported for papers in `source.ts`.

### 16. PR #125 — decision
`frontend/nested-definitions` conflicts on both contracts, `assessment.tsx`,
`papers/schema.ts` and `map.ts`. It makes the mapper read the spec-shaped
definitions client-side; #126 does it server-side. Close #125 once item 15
is decided, or rebase the parts that still apply (the "no headline from a
serialised object" rule is already covered server-side).

### 17. Views swallow exceptions into 500s with the message — S, backend
`api/views/scorecard.py:62-70, 83-91`: `logger.exception` and let DRF's
handler shape the error.

### 18. Docs overclaim — S
`src/app/bff/papers/README.md` says "O(1) per page request" and lists query
params (`starred`, `min_score`, `min_trl`, `max_trl`, `within_days`) the
endpoint does not implement; `papers/service.ts:5`, `schema.ts:6-7`,
`.env.example`, `docs/deploy-handoff.md` still call `composed` the default;
root README says Next.js 15 (package pins 16.3). `frontend/docs/backend-handoff.md`
still lists the scorecard as "wanted".

### 19. Author e-mails as mailto links — product call
`affiliation-flags.tsx:149-156` links any LLM-extracted string with an @,
next to the GDPR flag. Nobody has decided analysts should see author
addresses. `unpackFlag` re-parses values the backend already parsed and
diverges from it.

### 20. Small backend items — S
Dead `elif prim_val is None` in `ExtractionDefinition.__init__`;
`primary_frontend_metric` stored unsanitised while secondaries pass
`_sanitize_identifier`; neither validated against `response_schema` or
`exit_metrics`; `next`/`previous` on the scorecard drop `ordering`,
`search`, `screening_status`; `format_workspace_summary` invents
`created_at: 2026-01-01T00:00:00Z`; no data migration, so every existing
definition runs the fallback branch; `README.md` points at `uv run pytest`
while CI uses `manage.py test`.

---

## Kept from #126 (do not undo)
Constant query counts (14–16 per workspace scorecard, 12 per paper); exit
keys that hold objects yield a numeric headline server-side; the TRL
dimension matches the spec; `edition_detail?run_id=`; the run-list `defer`
of `stage_results`/`step_history`; the `qs = qs.filter` fixes in three
viewsets; `is_testing` in the throttle table; model fields, migration 0073,
the MCP tool with role checks, the admin badges; the sub-measure panels with
band, insight and evidence.

## Tests to add as items close
No spec-shaped definition fixture, no same-day rerun, no multi-metric paper
without `run_id` exist in the backend suite; `visible.test.ts` was deleted
with no replacement; several new frontend tests pin the English strings and
the formula and will need updating with items 11 and 13.
