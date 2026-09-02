import type { Lang } from '@/lib/i18n'

/**
 * Human wording for the simple crontab shapes the digest scheduler actually
 * uses ("M H * * *" and "M H * * D"). Anything fancier returns null and the
 * caller shows the raw expression — better honest than wrong.
 */
export function describeCron(expr: string, lang: Lang = 'en'): string | null {
  const fields = expr.trim().split(/\s+/)
  if (fields.length !== 5) return null
  const [m, h, dom, mon, dow] = fields
  if (!/^\d{1,2}$/.test(m) || !/^\d{1,2}$/.test(h) || dom !== '*' || mon !== '*') return null
  const minute = Number(m)
  const hour = Number(h)
  if (minute > 59 || hour > 23) return null
  const time = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`

  if (dow === '*') {
    return lang === 'de' ? `täglich um ${time} Uhr` : `daily at ${time}`
  }
  if (!/^\d$/.test(dow)) return null
  const day = Number(dow) % 7 // crontab allows 7 for Sunday
  // 2023-01-01 was a Sunday; offset by the crontab weekday (0 = Sunday).
  const weekday = new Intl.DateTimeFormat(lang === 'de' ? 'de-DE' : 'en-GB', {
    weekday: 'long',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(2023, 0, 1 + day)))
  return lang === 'de'
    ? `${weekday.toLowerCase()}s um ${time} Uhr` // "freitags um 09:00 Uhr"
    : `${weekday}s at ${time}` // "Fridays at 09:00"
}
