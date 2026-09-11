/**
 * Pure helpers for the screening log's PDF export: the file's name and text
 * as the embedded font can set it. Client-safe.
 */

/** ASCII slug: "Screening-Protokoll" → "screening-protokoll", "Hybrid Computing" → "hybrid-computing". */
export function slugify(s: string): string {
  return s
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** "screening-log-hybrid-computing-2026-09-10.pdf" — the kind in the reader's language, the domain, the day. */
export function screeningLogFilename(
  kind: string,
  domain: string | undefined,
  date: string,
): string {
  return [slugify(kind), domain ? slugify(domain) : '', date].filter(Boolean).join('-') + '.pdf'
}

// The spaces the German copy carries (U+00A0, U+2007, U+202F — DIN 5008's
// narrow no-break space before "%") have no glyph in the embedded font.
const FIXED_SPACES = new Set([0xa0, 0x2007, 0x202f])
const isControl = (c: number) => c < 0x20 && c !== 0x0a && c !== 0x09

/**
 * Text for the PDF: plain spaces only, no control characters, paragraph
 * breaks kept but never more than one blank line.
 */
export function pdfText(s: string | null | undefined): string {
  if (!s) return ''
  let out = ''
  for (const ch of s.normalize('NFC').replace(/\r\n?/g, '\n')) {
    const c = ch.codePointAt(0) ?? 0
    if (FIXED_SPACES.has(c)) out += ' '
    else if (!isControl(c)) out += ch
  }
  return out
    .replace(/[ \t]+/g, ' ')
    .replace(/ ?\n ?/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
