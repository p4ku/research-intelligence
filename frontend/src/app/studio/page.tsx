import { redirect } from 'next/navigation'

/** Runs are the Studio's home for now; config and evaluation land beside them. */
export default function StudioIndex() {
  redirect('/studio/runs')
}
