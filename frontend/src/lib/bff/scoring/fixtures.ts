/** Contract-shaped scoring fixture for the `stub` source and spec examples. Pure. */
import { fixturePapers, fixtureWorkspace } from '../papers/fixtures'
import type { WorkspaceScoring } from './schema'

const defs = fixtureWorkspace.definitions

export const fixtureScoring: WorkspaceScoring = {
  workspace_id: fixtureWorkspace.id,
  code: 'signal_score = fit_score * 0.7 + novelty_score * 10 * 0.3',
  code_source: 'stub',
  variables: defs.map((d) => ({
    key: d.key,
    definition_id: d.id,
    name: d.name,
    max: d.max,
    is_trl: d.is_trl,
  })),
  weights: [
    { key: 'fit_score', definition_id: defs[0].id, name: 'Fit Score', weight: 70 },
    { key: 'novelty_score', definition_id: defs[1].id, name: 'Novelty Score', weight: 30 },
    { key: 'trl_level', definition_id: defs[2].id, name: 'TRL Level', weight: 0 },
  ],
  weights_source: 'stub',
  example: {
    paper_id: fixturePapers[0].id,
    title: fixturePapers[0].title,
    signal_score: fixturePapers[0].signal_score,
    variables: fixturePapers[0].signal_score_details?.variables ?? {},
  },
}
