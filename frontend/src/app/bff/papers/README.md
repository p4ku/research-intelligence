# papers

## Purpose

Every paper in a workspace, scored: the backend's composite `signal_score`
plus one resolved value per extraction definition ("dimension"), with
rationale/evidence for the detail page. Feeds `/papers`, `/papers/[id]`, the
dashboard's run list, and the Ask paper palette.

## What the UI needs

- **Papers list** (`src/app/(sidebar)/papers/`): title, authors, screening
  status, ingest date, signal score, TRL + numeric dimensions; filter by
  screening (default: passed), sort by signal / recency / any dimension,
  full-text search. This consumer is behind the `all_papers` demo flag
  (`src/lib/features.ts`); the route below is not, and keeps serving detail,
  briefings, scoring and status whatever the cookie says.
- **Detail** (`/papers/[id]`): everything above plus the score formula and
  variables, per-dimension rationale/evidence/confidence, screening
  reasoning, arXiv/DOI links, storage keys.
- **Dashboard**: the papers of the latest completed run, sorted by signal.

## BFF routes

| Route                  | Query                                                                                                                                                                                                                                                                | Returns                                                                                                                                          |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /bff/papers`      | `workspace_id` (optional; absent = every domain the user belongs to), `page`, `page_size` (≤200), `screening=passed\|all\|<status>`, `ordering=[-]signal_score\|[-]created_at\|[-]dim:<key>`, `search`, `starred=1`, `min_score`, `min_trl`/`max_trl`, `within_days` | `ScoredPaperList` — a `ScoredPaperPage` plus `facets` (`PapersFacets`: the rail's corpus-wide counts, sort options, slider ceiling, `truncated`) |
| `GET /bff/papers/{id}` | —                                                                                                                                                                                                                                                                    | `{workspace: Workspace, paper: ScoredPaper}`                                                                                                     |

Schemas: `src/lib/bff/papers/schema.ts` (`ScoredPaper`, `Dimension`,
`SignalScoreDetails`). Errors are problem+json.

## Django endpoints we want

### `GET /api/workspaces/{workspace_id}/papers/`

Paginated scorecard, same params as the BFF route above (minus
`workspace_id`). Response: `{count, next, previous, results: ScoredPaper[]}`.

`ScoredPaper` (see `schema.ts` / `contract/openapi.json` for the authoritative
JSON Schema; `src/lib/bff/papers/fixtures.ts` for full examples):

```jsonc
{
  "id": "…uuid…",
  "workspace_id": "…uuid…",
  "pipeline_run_id": "…uuid…",
  "title": "…",
  "authors": ["A. Example", "B. Beispiel"],   // split from the comma-joined field
  "authors_raw": "A. Example, B. Beispiel",
  "abstract": "…",
  "doi": null,
  "arxiv_id": "2608.01234",
  "source": "arxiv",
  "screening_status": "full_text_passed",     // incl. 'accepted'
  "screening_reasoning": "…",
  "signal_score": 87.5,                        // PaperMetric.signal_score (run-matched, else newest)
  "signal_score_details": { "variables": {…}, "code_snippet": "…", "calculated_at": "…", "error": null },
  "dimensions": [                              // one per active definition, workspace order
    { "key": "fit_score", "definition_id": "…", "name": "Fit Score",
      "value": 92, "raw": "92", "max": 100, "is_trl": false,
      "rationale": "…", "evidence": ["…"], "confidence": 0.86,
      "validation_status": "pass", "review_required": false, "extraction_id": "…" }
  ],
  "pdf_key": null, "markdown_key": null,
  "source_url": "https://arxiv.org/abs/2608.01234",   // Paper.source_url verbatim
  "is_benchmark": false, "evaluation_label": null,
  "created_at": "2026-08-27T05:58:00Z"
}
```

**Derivation rules to port** (currently implemented frontend-side —
`src/lib/papers/map.ts`, acceptance cases in `src/lib/papers/map.test.ts`):

- `dimensions[].value`: prefer the numeric `metrics_data[key]`; else parse the
  extraction's exit metric (`Extraction.exit_metric` tiers, `_parse_numeric_value`
  semantics: `"85%"` → `0.85`, `"TRL 4"` → `4`, `"High"` → `null`). **A paper
  with no Extraction row for a definition has `value: null`** even though
  `metrics_data` pre-fills `0.0`.
- `key` = `_sanitize_identifier(definition.name)`.
- TRL detection: `\btrl\b` in the name; clamp 1–9; `max` 9. Other scales: a
  "(0-100)"-style hint in the definition, else corpus max (≤10 → 10, ≤100 → 100).
- `rationale`/`evidence`: from the nested `fields_data.evidence[]`
  (`{quote, rationale}`) or sibling `*reason*`/`*evidence*` keys.
- `signal_score`: the `PaperMetric` matching the paper's run, else the newest.
- `source_url`: `Paper.source_url` as the backend stores it, `null` when it has
  none or the value is not an `http(s)` URL. Never rebuilt from `arxiv_id` /
  `doi` — the backend owns the link rule. (The scorecard still also sends the
  old `pdf_url` key with the same value; the BFF ignores it.)

### `GET /api/papers/{paper_id}/scorecard/`

One paper in the same shape plus its workspace summary:
`{"workspace": Workspace, "paper": ScoredPaper}`. (Non-breaking — the existing
`/api/papers/{id}/` stays as-is.)

## Current implementation

`composed` (default): `src/lib/bff/papers/compose.ts` fetches the bare-array
`/api/papers/` + `/api/extractions/` + `/api/workspaces/` and derives
everything in memory — O(corpus) per page view, which is why this endpoint is
**P1**. `stub` serves `fixtures.ts`. `django` drains the desired list endpoint.

## Flip the flag

`BFF_SOURCE_PAPERS=django` → `/bff/status` shows `papers: django`, desired
endpoints `present`.

## curl

```bash
TOKEN=$(curl -s localhost:8000/api/auth/login/ -H 'content-type: application/json' \
  -d '{"username_or_email":"admin","password":"schwarz123!"}' | jq -r .access)
WS=$(curl -s localhost:8000/api/workspaces/ -H "authorization: Bearer $TOKEN" | jq -r '.[0].id')
# Desired:
curl -s "localhost:8000/api/workspaces/$WS/papers/?page_size=2&screening=passed" -H "authorization: Bearer $TOKEN"
# BFF (browser session cookie):
curl -s "localhost:3000/bff/papers?workspace_id=$WS&page_size=2" -b "sri_access=…"
```

## Done criteria

1. `bun run contract:check` → PASS for `papers.list.desired` and
   `papers.detail.desired` against a seeded backend.
2. `src/lib/papers/map.test.ts` cases reproduced in the backend's tests.
3. Fixtures refreshed from a real response; default source flipped to
   `django`; `docs/deploy-handoff.md` env table updated.
