/**
 * OUR stars contract: the calling user's starred papers and briefings — the
 * MVP's only front-end curation (one star per record, no collections). A
 * briefing is starred by the run that produced it (`run_id`), the same
 * identity the archive rail uses. Pure.
 */
import * as z from 'zod'

export const stars = z
  .object({
    /** Paper ids. */
    papers: z.array(z.uuid()),
    /** Pipeline-run ids (one briefing edition per completed run). */
    briefings: z.array(z.uuid()),
  })
  .meta({ id: 'Stars' })
export type Stars = z.infer<typeof stars>

export const starKind = z.enum(['paper', 'briefing'])
export type StarKind = z.infer<typeof starKind>

export const starUpdate = z
  .object({
    kind: starKind,
    id: z.uuid(),
    starred: z.boolean(),
  })
  .meta({ id: 'StarUpdate' })
export type StarUpdate = z.infer<typeof starUpdate>

export const emptyStars: Stars = { papers: [], briefings: [] }

/** Pure state transition for the client's optimistic update. */
export function applyStar(current: Stars, update: StarUpdate): Stars {
  const key = update.kind === 'paper' ? 'papers' : 'briefings'
  const without = current[key].filter((id) => id !== update.id)
  // Newest last, the order Django returns them in.
  return { ...current, [key]: update.starred ? [...without, update.id] : without }
}
