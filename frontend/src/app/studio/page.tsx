import { redirect } from 'next/navigation'

/**
 * Runs moved into the reading app (/runs). The Studio keeps the skeleton
 * gallery, which is a dev surface; sending the index there would surprise
 * anyone following an old link, so it lands on Runs instead.
 */
export default function StudioIndex() {
  redirect('/runs')
}
