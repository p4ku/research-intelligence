import type { Lang } from '@/lib/i18n'

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

/** The shape a permalink date must have before it is looked up (YYYY-MM-DD). */
export function isEditionDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
}

export { editionHref } from '@/lib/bff/briefings/href'
