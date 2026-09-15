import { fmt, formatNumber, localeOf, type Lang, type T } from '@/lib/i18n'

/**
 * Home's date words. Calendar days are rendered in UTC so the day never
 * shifts with the reader's zone (an edition is addressed by its UTC day —
 * see briefing/format.ts); clock times are UTC and labelled so, the way the
 * runs page does it. Pure, unit-tested.
 */

/** Noon UTC on the day, so no zone arithmetic can move it. */
function noon(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T12:00:00Z`)
}

function dayPart(iso: string, lang: Lang, opts: Intl.DateTimeFormatOptions): string {
  const s = noon(iso).toLocaleDateString(localeOf(lang), { timeZone: 'UTC', ...opts })
  // en-GB spells "Sept"; the spec writes "Sep". German's "Sept." is correct.
  return lang === 'de' ? s : s.replace('Sept', 'Sep')
}

/** "5 Sep 2026" / "5. Sept. 2026". Accepts a day or an instant (its UTC day). */
export function formatDay(iso: string, lang: Lang): string {
  return dayPart(iso, lang, { day: 'numeric', month: 'short', year: 'numeric' })
}

/**
 * A search window: "1–31 Aug 2026" within one month, "1 Aug–5 Sep 2026"
 * within one year, "1 Dec 2025–5 Jan 2026" across years. German keeps its
 * ordinal dots: "1.–31. Aug. 2026", "1. Aug.–5. Sept. 2026".
 */
export function formatPeriod(from: string, to: string, lang: Lang): string {
  const sameMonth = from.slice(0, 7) === to.slice(0, 7)
  const sameYear = from.slice(0, 4) === to.slice(0, 4)
  if (sameMonth) {
    const d = noon(from).getUTCDate()
    return `${d}${lang === 'de' ? '.' : ''}–${formatDay(to, lang)}`
  }
  const fromLabel = sameYear
    ? dayPart(from, lang, { day: 'numeric', month: 'short' })
    : formatDay(from, lang)
  return `${fromLabel}–${formatDay(to, lang)}`
}

/** "07:12" — the UTC clock time of an instant, in the reader's locale. */
export function formatClock(iso: string, lang: Lang = 'en'): string {
  return new Date(iso).toLocaleTimeString(localeOf(lang), {
    timeZone: 'UTC',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/**
 * "12:03 UTC" — the clock that tells two same-day briefings of one domain
 * apart, in the ledgers' Generated cell and the edition page's notice.
 * Labelled, the way the runs page and Home's "started" cell do it.
 */
export function clockStamp(iso: string, lang: Lang = 'en'): string {
  return `${formatClock(iso, lang)} UTC`
}

/** "11 Sep 2026 · 06:06 UTC" — full date + time stamp. */
export function formatTimestamp(iso: string, lang: Lang = 'en'): string {
  return `${formatDay(iso, lang)} · ${clockStamp(iso, lang)}`
}

/**
 * The Period cell: the window a run searched. Explicit dates read as a
 * range, a relative window as "Last N days", and a run that recorded
 * neither (captures from before the field existed) falls back to the day
 * it was triggered.
 */
export function periodLabel(
  run: {
    period_start: string | null
    period_end: string | null
    lookback_days: number | null
    run_date: string
  },
  t: T,
  lang: Lang,
): string {
  if (run.period_start && run.period_end)
    return formatPeriod(run.period_start, run.period_end, lang)
  if (run.period_start) return fmt(t('From {date}'), { date: formatDay(run.period_start, lang) })
  if (run.period_end) return fmt(t('Until {date}'), { date: formatDay(run.period_end, lang) })
  // "Letzte 1 Tage" is not a sentence: one day gets its own key.
  if (run.lookback_days === 1) return t('Last day')
  if (run.lookback_days)
    return fmt(t('Last {n} days'), { n: formatNumber(run.lookback_days, lang) })
  return formatDay(run.run_date, lang)
}

/** YYYY-MM-DD, `days` before the given day (UTC arithmetic). */
export function shiftDays(iso: string, days: number): string {
  const d = noon(iso)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Up to three names, then "et al." — the authors line under a title. */
export function formatAuthors(authors: string[]): string {
  const shown = authors.slice(0, 3).join(', ')
  return authors.length > 3 ? `${shown} et al.` : shown
}
