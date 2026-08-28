# scoring

## Purpose

The read-only **Scoring** page (`/scoring`): how this workspace ranks papers —
the signal-score formula, the variables it reads, per-dimension weights, and
one worked example. Users never edit; the formula stays a backend-owned
Python snippet (`Workspace.signal_score_code`).

## BFF route

`GET /bff/scoring?workspace_id=` → `WorkspaceScoring`
(`src/lib/bff/scoring/schema.ts`).

## Django endpoint we want

`GET /api/workspaces/{workspace_id}/scoring/` (read-only) →

```jsonc
{
  "workspace_id": "…",
  "code": "signal_score = fit_score * 0.7 + …",   // Workspace.signal_score_code
  "code_source": "workspace",
  "variables": [{ "key": "fit_score", "definition_id": "…", "name": "Fit Score", "max": 100, "is_trl": false }],
  "weights": [{ "key": "fit_score", "definition_id": "…", "name": "Fit Score", "weight": 70 }],
  "weights_source": "backend",
  "example": { "paper_id": "…", "title": "…", "signal_score": 87.5, "variables": { "fit_score": 92 } }
}
```

The interesting ask is `weights`: a structured list kept alongside the code
snippet (author them together) so the UI can show the weighting without
parsing Python. P2.

## Current implementation

`composed` (default): `code` and the example come from the newest scored
paper's `metrics[].signal_score_details` (the workspace serializer does not
expose `signal_score_code`); variables from the workspace's definitions;
weights are an **even placeholder split flagged `weights_source: 'stub'`**
(the page says so). `stub` serves `fixtures.ts`.

## Done criteria

`contract:check` PASS for `scoring.get.desired`; default flipped to `django`;
the placeholder-weights note disappears.
