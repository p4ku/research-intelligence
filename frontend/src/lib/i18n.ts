import { de } from '@/locales/de'

// Demo-scale i18n: English is the source of truth in the JSX; German is a
// dictionary keyed by the exact English string. Unlike preview mode
// (localStorage), the language lives in a cookie because most pages are
// server components and need it at render time.
export type Lang = 'en' | 'de'
// Optional gettext-style context disambiguates English words that translate
// differently by meaning (e.g. "Open" the button vs. "open" the status).
// Dictionary key for a contextualized string: '<ctx>|<english>'.
export type T = (s: string, ctx?: string) => string

export const LANG_COOKIE = 'rs-lang'

const warned = new Set<string>()

export function makeT(lang: Lang): T {
  if (lang === 'en') return (s) => s
  return (s, ctx) => {
    const hit = (ctx !== undefined ? de[`${ctx}|${s}`] : undefined) ?? de[s]
    if (hit !== undefined) return hit
    if (process.env.NODE_ENV !== 'production' && !warned.has(s)) {
      warned.add(s)
      console.warn(`[i18n] missing de translation: "${s}"`)
    }
    return s
  }
}

// Placeholder interpolation for translated templates:
//   fmt(t('Showing {n} papers'), { n })
export function fmt(s: string, vars: Record<string, string | number>): string {
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''))
}

// Locale-aware short date ("Jun 3, 2026" / "3. Juni 2026"). Lives here — not
// in a client component — so server components can call it too.
export function formatDate(iso: string, lang: Lang = 'en'): string {
  return new Date(iso).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
