/**
 * Template prose for editions until the backend writes model prose
 * (`in_brief_source: 'template'`). Honest by construction: every number and
 * title comes from the run. Bilingual: unlike backend-generated content
 * (which is never translated), these sentences are composed here, so they
 * follow the interface language. Pure, unit-tested.
 */
import type { Lang } from '@/lib/i18n'
import type { EditionPaper } from './schema'

const short = (title: string) => title.split(':')[0]

export function templateProse(
  input: {
    workspaceName: string
    fetched: number
    passedScreening: number
    surfaced: number
    papers: EditionPaper[]
  },
  lang: Lang = 'en',
): { title: string; in_brief: string } {
  const { workspaceName, fetched, passedScreening, surfaced, papers } = input
  const [top, ...rest] = papers
  const de = lang === 'de'
  const quote = de ? (s: string) => `„${s}“` : (s: string) => `“${s}”`

  if (!top) {
    return {
      title: de ? 'Ein ruhiger Lauf' : 'A quiet run',
      in_brief: de
        ? `Der Scan ${quote(workspaceName)} hat ${fetched} ${fetched === 1 ? 'Paper' : 'Papers'} geladen; keines hat das Screening für dieses Briefing bestanden.`
        : `The ${workspaceName} scan fetched ${fetched} paper${fetched === 1 ? '' : 's'}; none cleared screening for this briefing.`,
    }
  }

  const also = rest
    .slice(0, 2)
    .map((p) => quote(short(p.title)))
    .join(de ? ' und ' : ' and ')
  const sentences = de
    ? [
        `Der Scan ${quote(workspaceName)} hat ${fetched} Papers geladen, ${passedScreening} durch das Screening gebracht und ${surfaced} für dieses Briefing ausgewählt.`,
        top.signal_score !== null
          ? `An der Spitze: ${quote(short(top.title))} mit Signal ${Math.round(top.signal_score)}.`
          : `An der Spitze: ${quote(short(top.title))}.`,
      ]
    : [
        `The ${workspaceName} scan fetched ${fetched} papers, passed ${passedScreening} through screening, and surfaced ${surfaced} for this briefing.`,
        top.signal_score !== null
          ? `Leading the list: ${quote(short(top.title))} at signal ${Math.round(top.signal_score)}.`
          : `Leading the list: ${quote(short(top.title))}.`,
      ]
  if (also) sentences.push(de ? `Ebenfalls bemerkenswert: ${also}.` : `Also notable: ${also}.`)
  return { title: short(top.title), in_brief: sentences.join(' ') }
}
