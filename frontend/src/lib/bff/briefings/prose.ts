/**
 * Template prose for editions until the backend writes model prose
 * (`in_brief_source: 'template'`). Honest by construction: every number and
 * title comes from the run. English only — generated/derived content is
 * never translated. Pure, unit-tested.
 */
import type { EditionPaper } from './schema'

const short = (title: string) => title.split(':')[0]

export function templateProse(input: {
  workspaceName: string
  fetched: number
  passedScreening: number
  surfaced: number
  papers: EditionPaper[]
}): { title: string; in_brief: string } {
  const { workspaceName, fetched, passedScreening, surfaced, papers } = input
  const [top, ...rest] = papers

  if (!top) {
    return {
      title: 'A quiet run',
      in_brief: `The ${workspaceName} scan fetched ${fetched} paper${fetched === 1 ? '' : 's'}; none cleared screening for this briefing.`,
    }
  }

  const also = rest
    .slice(0, 2)
    .map((p) => `“${short(p.title)}”`)
    .join(' and ')
  const sentences = [
    `The ${workspaceName} scan fetched ${fetched} papers, passed ${passedScreening} through screening, and surfaced ${surfaced} for this briefing.`,
    top.signal_score !== null
      ? `Leading the list: “${short(top.title)}” at signal ${Math.round(top.signal_score)}.`
      : `Leading the list: “${short(top.title)}”.`,
  ]
  if (also) sentences.push(`Also notable: ${also}.`)
  return { title: short(top.title), in_brief: sentences.join(' ') }
}
