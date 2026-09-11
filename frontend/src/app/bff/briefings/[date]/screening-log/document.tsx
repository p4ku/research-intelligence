import 'server-only'

import { formatEditionDate } from '@/app/(sidebar)/briefing/format'
import { pdfText } from '@/lib/bff/briefings/export'
import type { Edition } from '@/lib/bff/briefings/schema'
import { fmt, formatNumber, localeOf, type Lang, type T } from '@/lib/i18n'
import { Document, Font, Page, StyleSheet, Text, View, renderToBuffer } from '@react-pdf/renderer'
import path from 'node:path'

/**
 * The screening log as a document: the run's funnel, then every paper that
 * screened out with the model's reasoning, verbatim. A4, set in Switzer —
 * the app's own face, embedded under src/fonts/SWITZER-LICENSE.txt §03 —
 * with a running head and page numbers. The sizes are points.
 */

const FONT_DIR = path.join(process.cwd(), 'src', 'fonts')

// Registered once per process, not per module evaluation: react-pdf's font
// store is global, and a dev reload that registers the family again was
// measured at ten times the render time (44 s against 4.6 s for 64 pages).
const registry = globalThis as { __screeningLogFonts?: true }
function registerFonts() {
  if (registry.__screeningLogFonts) return
  registry.__screeningLogFonts = true
  Font.register({
    family: 'Switzer',
    fonts: [
      { src: path.join(FONT_DIR, 'Switzer-Regular.otf'), fontWeight: 400 },
      { src: path.join(FONT_DIR, 'Switzer-Semibold.otf'), fontWeight: 600 },
    ],
  })
  // Words stay whole — the columns are wide enough — except a token longer
  // than the title column (a URL, an identifier), which gets break points
  // so the line breaker is never handed something it cannot place.
  Font.registerHyphenationCallback((word) =>
    word.length <= LONGEST_WHOLE_WORD ? [word] : (word.match(/.{1,12}/g) ?? [word]),
  )
}

const LONGEST_WHOLE_WORD = 24

// zinc-950 / 700 / 500 / 400 / 200, and the app's accent.
const ink = {
  text: '#09090b',
  prose: '#3f3f46',
  muted: '#71717a',
  faint: '#a1a1aa',
  line: '#e4e4e7',
  accent: '#00c3cd',
}

const MARGIN = 56

const s = StyleSheet.create({
  page: {
    paddingTop: 76,
    paddingBottom: 68,
    paddingHorizontal: MARGIN,
    fontFamily: 'Switzer',
    fontSize: 9.5,
    color: ink.text,
  },
  runningHead: {
    position: 'absolute',
    top: 34,
    left: MARGIN,
    right: MARGIN,
    flexDirection: 'row',
    justifyContent: 'space-between',
    fontSize: 7,
    letterSpacing: 1,
    textTransform: 'uppercase',
    color: ink.faint,
  },
  runningFoot: {
    position: 'absolute',
    bottom: 34,
    left: MARGIN,
    right: MARGIN,
    flexDirection: 'row',
    justifyContent: 'space-between',
    fontSize: 7.5,
    color: ink.faint,
  },
  title: { fontSize: 22, fontWeight: 600, letterSpacing: -0.3 },
  meta: { marginTop: 6, color: ink.muted },
  band: {
    marginTop: 26,
    paddingTop: 14,
    borderTopWidth: 0.5,
    borderTopColor: ink.line,
    flexDirection: 'row',
  },
  stat: { width: '33%' },
  statLabel: { fontSize: 7, letterSpacing: 1, textTransform: 'uppercase', color: ink.faint },
  statValue: { marginTop: 3, fontSize: 18, fontWeight: 600, letterSpacing: -0.2 },
  section: { marginTop: 32, flexDirection: 'row', alignItems: 'center' },
  square: { width: 5, height: 5, marginRight: 6, backgroundColor: ink.accent },
  sectionLabel: {
    fontSize: 7,
    fontWeight: 600,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: ink.muted,
  },
  thead: {
    marginTop: 12,
    paddingBottom: 6,
    borderBottomWidth: 0.5,
    borderBottomColor: ink.faint,
    flexDirection: 'row',
    fontSize: 7,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    color: ink.faint,
  },
  row: {
    paddingVertical: 8,
    borderBottomWidth: 0.5,
    borderBottomColor: ink.line,
    flexDirection: 'row',
  },
  paper: { width: '34%', paddingRight: 12 },
  // A unitless lineHeight multiplies the node's own fontSize — or react-pdf's
  // 18pt default when the node inherits it — so the title names its size.
  paperTitle: { fontSize: 9.5, fontWeight: 600, lineHeight: 1.35 },
  source: { width: '12%', paddingRight: 12, fontSize: 8, color: ink.faint },
  reason: { width: '54%', fontSize: 9, lineHeight: 1.45, color: ink.prose },
  empty: { marginTop: 12, color: ink.muted },
})

// A reason this long may not fit one page whole; let it break rather than
// push a whole page of white ahead of it.
const KEEP_WHOLE_UNDER = 1200

export type ScreeningLogDocumentProps = {
  edition: Edition
  /** The domain's display name; the edition's own when the list did not have it. */
  domain: string | undefined
  lang: Lang
  t: T
  exportedAt: Date
}

function stamp(date: Date, lang: Lang): string {
  return `${date.toLocaleString(localeOf(lang), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  })} UTC`
}

export function ScreeningLogDocument({
  edition,
  domain,
  lang,
  t,
  exportedAt,
}: ScreeningLogDocumentProps) {
  const kind = t('Screening log')
  const day = formatEditionDate(edition.date, lang)
  const where = [domain && pdfText(domain), day].filter(Boolean).join(' · ')
  const run = [
    `${t('Run')} ${edition.run_id.slice(0, 8)}`,
    edition.generated_at && stamp(new Date(edition.generated_at), lang),
  ]
    .filter(Boolean)
    .join(' · ')
  const n = (v: number) => formatNumber(v, lang)
  const stats = [
    [t('Screened'), n(edition.funnel.fetched)],
    [t('Analysed'), n(edition.funnel.passed_screening)],
    [t('Screened out'), n(edition.exclusions.length)],
  ]

  return (
    <Document title={`${kind} · ${where}`} author="Research Intelligence" language={lang}>
      <Page size="A4" style={s.page}>
        <View style={s.runningHead} fixed>
          <Text>Research Intelligence · {kind}</Text>
          <Text>{where}</Text>
        </View>

        <Text style={s.title}>{kind}</Text>
        <Text style={s.meta}>{where}</Text>
        <Text style={s.meta}>{run}</Text>

        <View style={s.band}>
          {stats.map(([label, value]) => (
            <View key={label} style={s.stat}>
              <Text style={s.statLabel}>{label}</Text>
              <Text style={s.statValue}>{value}</Text>
            </View>
          ))}
        </View>

        <View style={s.section} minPresenceAhead={80}>
          <View style={s.square} />
          <Text style={s.sectionLabel}>{t('Screened out')}</Text>
        </View>

        {edition.exclusions.length === 0 ? (
          <Text style={s.empty}>{t('Nothing was screened out in this run.')}</Text>
        ) : (
          <>
            <View style={s.thead} minPresenceAhead={60}>
              <Text style={s.paper}>{t('Paper')}</Text>
              <Text style={s.source}>{t('Source')}</Text>
              <Text style={s.reason}>{t('Why it did not pass')}</Text>
            </View>
            {edition.exclusions.map((ex) => {
              const reason = pdfText(ex.reason) || '—'
              return (
                <View key={ex.paper_id} style={s.row} wrap={reason.length >= KEEP_WHOLE_UNDER}>
                  <View style={s.paper}>
                    <Text style={s.paperTitle}>{pdfText(ex.title)}</Text>
                  </View>
                  <Text style={s.source}>{pdfText(ex.source)}</Text>
                  <Text style={s.reason}>{reason}</Text>
                </View>
              )
            })}
          </>
        )}

        <View style={s.runningFoot} fixed>
          <Text>{fmt(t('Exported {when}'), { when: stamp(exportedAt, lang) })}</Text>
          <Text
            render={({ pageNumber, totalPages }) =>
              fmt(t('Page {n} of {total}'), { n: pageNumber, total: totalPages ?? pageNumber })
            }
          />
        </View>
      </Page>
    </Document>
  )
}

/** The document as bytes. */
export async function renderScreeningLog(props: ScreeningLogDocumentProps): Promise<Buffer> {
  registerFonts()
  return renderToBuffer(<ScreeningLogDocument {...props} />)
}
