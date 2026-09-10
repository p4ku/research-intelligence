import type { T } from '@/lib/i18n'
import type { Dimension } from './types'

/**
 * Display name for a scored dimension. The names arrive from the backend —
 * they are the workspace's extraction definitions, so most of them are the
 * domain's own words and stay exactly as written. The handful that are the
 * product's own vocabulary (the dimensions every domain scores, and the two
 * names the frontend itself supplies) do have a German reading, and the paper
 * page is the busiest screen in the app, so they are mapped here.
 *
 * One mapper, called wherever a dimension name reaches the page — the card's
 * stats, the rail's bars, the radar's axes, the assessment's headings, its
 * sub-measure rows and its fact terms — so a bar and the article it links to
 * cannot end up saying two different things. Names outside the table come
 * back unchanged; insight, evidence and rationale prose is never touched.
 *
 * The lookup is written as a switch of literal `t()` calls because the
 * dictionary guard (lib/i18n.test.ts) can only see keys spelled out in the
 * source: a table of strings fed to `t(x)` would be invisible to it.
 */
export function dimensionLabel(name: string, t: T): string {
  switch (name.trim().toLowerCase()) {
    case 'rigour':
      return t('Rigour', 'dimension')
    case 'novelty':
      return t('Novelty', 'dimension')
    case 'significance':
      return t('Significance', 'dimension')
    case 'readiness':
      return t('Readiness', 'dimension')
    case 'schwarz fit':
      return t('Schwarz Fit', 'dimension')
    // The ledger's own name for the same measure, which some domains send as
    // the dimension name too.
    case 'fit score':
      return t('Fit score')
    case 'research quality':
      return t('Research Quality', 'dimension')
    // Names the frontend supplies itself: the "Core technology" fact it
    // renames (papers/[id]/assessment.tsx) and the fallback an extraction
    // whose definition was deleted falls back to (papers/map.ts).
    case 'technology being assessed':
      return t('Technology being Assessed')
    case 'extraction':
      return t('Extraction')
    default:
      return name
  }
}

/**
 * A dimension's name at its shortest: "Sovereign Cloud & Commercial
 * Viability" → "Sovereign Cloud"; a TRL definition is just "TRL". Shared by
 * the paper page's rail (bars, radar) and a briefing's sort options, so the
 * same dimension reads the same in both.
 *
 * The whole name is offered to the mapper first: a mapped dimension ("Fit
 * score", "Schwarz Fit") is product vocabulary and keeps the reading the
 * heading and the assessment give it, whatever punctuation it contains. Only
 * a name the mapper does not know — a domain's own wording — is shortened,
 * and then the shortened half goes through the mapper too, so a compound like
 * "Novelty (weighted)" still reads as the dimension.
 */
export function dimensionShortName(d: Pick<Dimension, 'name' | 'is_trl'>, t: T): string {
  if (d.is_trl) return 'TRL'
  const mapped = dimensionLabel(d.name, t)
  if (mapped !== d.name) return mapped
  return dimensionLabel(d.name.split(/ \(| & /)[0]!, t)
}
