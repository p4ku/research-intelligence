import type { Lang, T } from '@/lib/i18n'

/** "Friday, 3 July 2026" / "Freitag, 3. Juli 2026" — the edition's display date. */
export function formatEditionDate(iso: string, lang: Lang): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

/**
 * The three funnel cells an edition shows. Lives here, not in a `sections.tsx`,
 * because both skeletons need it and those modules import `server-only`
 * services: a client component importing a skeleton would fail the build.
 * Only the last cell's sub line differs between the edition and its log.
 */
export function funnelCopy(t: T, surfacedSub: string) {
  return [
    { label: t('Screened'), sub: t('matched the focus fields') },
    { label: t('Included'), sub: t('cleared the signal bar') },
    { label: t('In the briefing'), sub: surfacedSub },
  ]
}

/** The shape a permalink date must have before it is looked up (YYYY-MM-DD). */
export function isEditionDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
}
