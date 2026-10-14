import type { VisualCitation } from '@/lib/bff/chat/schema'
import { describe, expect, test } from 'bun:test'
import type { ComponentProps, ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { Components } from 'react-markdown'
import { AnswerMarkdown, componentsFor, normalizeLooseFormatting } from './answer-markdown'

const html = (text: string, streaming = false) =>
  renderToStaticMarkup(<AnswerMarkdown text={text} streaming={streaming} />)

const MONO = 'font-mono'
const CARET = '▍'

describe('AnswerMarkdown', () => {
  test('renders the markdown the model actually emits', () => {
    const out = html(
      '### Key finding\n\nThe **method** *works*.\n\n- a\n- b\n\n---\n\n1. one\n2. two',
    )
    expect(out).toContain('<h4')
    expect(out).toContain('Key finding')
    expect(out).not.toContain('###')
    expect(out).toContain('<strong')
    expect(out).toContain('<em')
    expect(out).not.toContain('**')
    expect(out.match(/<li/g)).toHaveLength(4)
    expect(out).toContain('<ul')
    expect(out).toContain('<ol')
    expect(out).toContain('<hr')
  })

  test('normalizes loose markdown delimiters with inner whitespace into proper formatting', () => {
    expect(normalizeLooseFormatting('***comment 3 Bold ***')).toBe('***comment 3 Bold***')
    expect(normalizeLooseFormatting('*** C ***')).toBe('***C***')
    expect(normalizeLooseFormatting('** V **')).toBe('**V**')
    expect(normalizeLooseFormatting('* italic *')).toBe('*italic*')

    const boldWithSpaces = html('** V **')
    expect(boldWithSpaces).toContain('<strong')
    expect(boldWithSpaces).toContain('>V</strong>')
    expect(boldWithSpaces).not.toContain('**')

    const boldItalic = html('***comment 3 Bold ***')
    expect(boldItalic).toContain('<strong')
    expect(boldItalic).toContain('<em')
    expect(boldItalic).toContain('comment 3 Bold')
    expect(boldItalic).not.toContain('***')

    // Bullet points with * must not be confused with italics
    const bullets = '* Ala\n* Ma\n* Kota'
    expect(normalizeLooseFormatting(bullets)).toBe(bullets)
    const bulletsHtml = html(bullets)
    expect(bulletsHtml).toContain('<ul')
    expect(bulletsHtml).toContain('>Ala</li>')
    expect(bulletsHtml).toContain('>Ma</li>')
    expect(bulletsHtml).toContain('>Kota</li>')
    expect(bulletsHtml).not.toContain('<em')
  })

  test('renders single line breaks within paragraphs as br tags', () => {
    const out = html('dcssff\nsfsfs\nfsfsfsdf')
    expect(out).toContain('<br/>')
    expect(out).toContain('dcssff<br/>\nsfsfs<br/>\nfsfsfsdf')
  })

  test('splits paragraphs on blank lines', () => {
    expect(html('Text\n\nmore').match(/<p>/g)).toHaveLength(2)
  })

  test('renders GFM tables inside a scroll container', () => {
    const out = html('| a | b |\n|---|---|\n| 1 | 2 |')
    expect(out).toContain('overflow-x-auto')
    expect(out).toContain('<table')
    expect(out).toContain('<th')
    expect(out).toContain('<td')
  })

  test('does not read a single tilde as strikethrough', () => {
    expect(html('~5% to ~10%')).not.toContain('<del')
    expect(html('~~gone~~')).toContain('<del')
  })

  test('wraps figures in mono, including inside emphasis', () => {
    const out = html('Accuracy rose to 94.0% (3.2x) with (+12).')
    expect(out.match(new RegExp(MONO, 'g'))).toHaveLength(3)
    expect(out).toContain('>94.0%</span>')
    expect(out).toContain('>3.2x</span>')
    expect(out).toContain('>(+12)</span>')

    const bold = html('**31%** better')
    expect(bold).toMatch(/<strong[^>]*><span[^>]*font-mono[^>]*>31%<\/span><\/strong>/)
  })

  test('leaves bare references and citation markers as text unless citations are on', () => {
    const src = 'See [1] and [Page 7, Fig 4b, box_2d: [1, 2, 3, 4], quote: "x"].'
    const out = html(src)
    expect(out).not.toContain('<a ')
    expect(out).toContain('[1]')
    expect(out).toContain('box_2d: [1, 2, 3, 4]')
  })

  test('never renders raw HTML or unsafe URL schemes', () => {
    expect(html('<script>alert(1)</script>')).not.toContain('<script')
    const inlineHtml = html('a <b>x</b> b')
    expect(inlineHtml).not.toContain('<b>')
    expect(inlineHtml).toContain('x')
    const unsafe = html('[x](javascript:alert(1))')
    expect(unsafe).not.toContain('javascript:')
    expect(unsafe).not.toContain('<a ')
    expect(unsafe).toContain('x')
    expect(html('![pic](https://example.com/p.png)')).not.toContain('<img')
  })

  test('safe links open in a new tab without an opener', () => {
    const out = html('[arXiv](https://arxiv.org/abs/2603.26644)')
    expect(out).toContain('href="https://arxiv.org/abs/2603.26644"')
    expect(out).toContain('target="_blank"')
    expect(out).toContain('rel="noopener noreferrer"')
  })

  test('streaming: the caret ends the block being written', () => {
    // remark-rehype puts "\n" text nodes between block elements.
    const compact = (s: string) => s.replace(/>\n</g, '><')
    const caretSpan = `<span[^>]*>${CARET}</span>`

    const list = compact(html('- a\n- b', true))
    expect(list.endsWith(`${CARET}</span></li></ul></div>`)).toBe(true)

    const bold = html('**bold', true)
    expect(bold).toContain('<strong')
    expect(bold).toMatch(new RegExp(`</strong>${caretSpan}</p>`))

    // The sentinel is preceded by a space so a closing `_` still closes.
    const under = html('some _em_', true)
    expect(under).toMatch(new RegExp(`<em[^>]*>em</em>${caretSpan}</p>`))

    const trailing = html('First line.\n\n', true)
    expect(trailing.match(/<p>/g)).toHaveLength(1)
    expect(trailing).toContain('First line.<span')

    // After a closed fence or a table row the caret gets its own line — glued
    // on, it would reopen the fence or become a dropped extra cell.
    const fence = compact(html('```\ncode\n```', true))
    expect(fence).toMatch(new RegExp(`</pre><p>${caretSpan}</p></div>$`))
    const table = compact(html('| a | b |\n|---|---|\n| 1 | 2 |', true))
    expect(table).toMatch(new RegExp(`</table></div><p>${caretSpan}</p></div>$`))
  })

  test('not streaming: no caret, no repair', () => {
    const out = html('- a\n- b')
    expect(out).not.toContain(CARET)
  })
})

describe('AnswerMarkdown math', () => {
  // KaTeX keeps the TeX source in a hidden MathML <annotation>; the visible
  // half is .katex-html, so "rendered" means the source is out of the text.
  const visible = (out: string) => out.replace(/<annotation[^>]*>[\s\S]*?<\/annotation>/g, '')

  test('typesets the inline LaTeX the OCR step leaves in the text', () => {
    const out = html('no defined state space $\\mathcal{S}$ or reward function $\\mathcal{R}$')
    expect(out.match(/class="katex"/g)).toHaveLength(2)
    expect(visible(out)).not.toContain('\\mathcal')
    expect(visible(out)).not.toContain('$')
  })

  test('gives a formula on its own line a display block', () => {
    for (const src of [
      'The objective:\n\n$$\\alpha_1 = 0.63$$\n',
      'The objective:\n\n$$\n\\alpha_1 = 0.63\n$$\n',
      'The objective:\n\n\\[\\alpha_1 = 0.63\\]\n',
    ]) {
      const out = html(src)
      expect(out).toContain('katex-display')
      expect(visible(out)).not.toContain('$')
    }
  })

  test('reads the \\( \\) delimiter inline and leaves an unclosed one alone', () => {
    const out = html('fixed weights \\(\\alpha_1 = 0.63\\) with no ablation')
    expect(out).toContain('class="katex"')
    expect(out).not.toContain('katex-display')
    // Unclosed, so it stays prose — markdown eats the escaping backslash.
    expect(html('a \\(b')).toContain('a (b')
  })

  test('leaves LaTeX quoted as code as source', () => {
    const fenced = html('```\n\\[x\\]\n```')
    expect(fenced).toContain('<pre')
    expect(fenced).not.toContain('class="katex"')
    expect(fenced).toContain('\\[x\\]')
    expect(html('`$x$`')).not.toContain('class="katex"')
  })

  test('an unparseable or half-streamed formula degrades to text', () => {
    const bad = html('$\\frac{1}{$')
    expect(bad).toContain('katex-error')
    expect(bad).toContain('\\frac{1}{')
    expect(bad).toContain('var(--negative)')

    // A formula still being written is held back rather than shown as source
    // and swapped for math a moment later; the caret waits with it.
    const open = html('routing over $\\mathcal{S', true)
    expect(open).not.toContain('mathcal')
    expect(open).toContain('routing over')
    expect(open).toContain(CARET)
    expect(html('routing over $\\mathcal{S}$ and', true)).toContain('class="katex"')
  })

  test('holds back an open display block too', () => {
    const open = html('The objective:\n\n$$\n\\alpha_1 = 0.63', true)
    expect(open).toContain('The objective:')
    expect(open).not.toContain('alpha')
    expect(html('The objective:\n\n$$\n\\alpha_1 = 0.63\n$$\n', true)).toContain('katex-display')
  })

  test('a lone $ in prose is not mistaken for an open formula', () => {
    const price = html('a run costs about $5 and the next', true)
    expect(price).toContain('the next')
    expect(price).toContain('$5')
  })
})

describe('AnswerMarkdown citation chips', () => {
  const chips = (
    text: string,
    opts: { citations?: VisualCitation[]; anchor?: string; streaming?: boolean } = {},
  ) =>
    renderToStaticMarkup(
      <AnswerMarkdown
        text={text}
        citations={opts.citations ?? []}
        citationAnchor={opts.anchor}
        streaming={opts.streaming}
      />,
    )
  const MARKER = '[Page 7, Fig 4b, box_2d: [320, 150, 680, 890], quote: "up 31%"]'
  /**
   * The `components` map AnswerMarkdown hands react-markdown for one render.
   * `memo` keeps the render function on `.type`, so this reads the real call
   * site — the map a future edit would rebuild per render.
   */
  const renderOnce = AnswerMarkdown as unknown as {
    type: (
      props: ComponentProps<typeof AnswerMarkdown>,
    ) => ReactElement<{ children: ReactElement<{ components: Components }> }>
  }
  const markdownRenderers = (props: ComponentProps<typeof AnswerMarkdown>) =>
    renderOnce.type(props).props.children.props.components
  const leaks = (out: string) => /[]/.test(out)

  test('turns a marker into a p. N · label chip and leaves bare references alone', () => {
    const out = chips(`See [1] and ${MARKER}.`)
    expect(out).toContain('p. 7 · Fig 4b')
    expect(out).toContain('title="up 31%"')
    expect(out).not.toContain('box_2d')
    expect(out).not.toContain('<a ')
    expect(out).toContain('[1]')
    expect(leaks(out)).toBe(false)
  })

  test('renders chips inside emphasis, list items and code', () => {
    const out = chips('**see [Page 7, Fig 4b]**\n\n- item [Page 2, Table 1]\n\n`x [Page 3, Fig 1]`')
    expect(out).toMatch(/<strong[^>]*>see <span[^>]*>p\. 7 · Fig 4b<\/span><\/strong>/)
    expect(out).toMatch(/<li[^>]*>item <span[^>]*>p\. 2 · Table 1<\/span><\/li>/)
    expect(out).toMatch(/<code[^>]*>x <span[^>]*>p\. 3 · Fig 1<\/span><\/code>/)
    expect(leaks(out)).toBe(false)
  })

  test('shows the verified tick only when the matched citation is verified', () => {
    const verified = chips(MARKER, {
      citations: [{ page: 7, label: 'Fig 4b', verified_in_source: true }],
    })
    expect(verified).toContain('Verified in source')
    expect(chips(MARKER)).not.toContain('Verified in source')
    expect(
      chips(MARKER, { citations: [{ page: 7, label: 'Fig 4b', verified_in_source: false }] }),
    ).not.toContain('Verified in source')
  })

  test('links to the citation card when an anchor is given; duplicates share it', () => {
    const out = chips(`${MARKER} and again ${MARKER}`, { anchor: 'vc-3' })
    expect(out.match(/href="#vc-3-0"/g)).toHaveLength(2)
    expect(out).not.toContain('#vc-3-1')
  })

  test('streaming: a half-arrived marker is held back and the caret stays last', () => {
    const open = chips('see [Page 7, Fig', { streaming: true })
    expect(open).not.toContain('Fig')
    expect(open).not.toContain('[')
    expect(open).toMatch(/see<span[^>]*>▍<\/span><\/p><\/div>$/)

    const closed = chips('x [Page 7, Fig 4b] y', { streaming: true })
    expect(closed).toContain('p. 7 · Fig 4b')
    expect(closed).toMatch(/y<span[^>]*>▍<\/span><\/p><\/div>$/)
    expect(leaks(closed)).toBe(false)
  })

  test('hands Markdown the same renderers as a stream grows, so it never remounts', () => {
    // A components map rebuilt per render is a fresh element type for every <p>
    // and <li>, so React remounts the whole answer on each token and every word
    // replays its unveil — the answer flickers as a blur from the first chip on.
    // Reading the map off the rendered tree pins the call site, not just the
    // cache: it is the same object as the text grows and as citations arrive.
    const growing = markdownRenderers({ text: `a ${MARKER}`, citations: [], streaming: true })
    const grown = markdownRenderers({ text: `a b ${MARKER}`, citations: [], streaming: true })
    const uncited = markdownRenderers({ text: 'a b', citations: [], streaming: true })
    expect(growing).toBe(grown)
    expect(growing).toBe(uncited)
    expect(growing).toBe(componentsFor({ stats: true, unveil: false, caret: true }))

    // And the chips still resolve through the tree rather than a closure.
    expect(chips(`a ${MARKER}`, { streaming: true })).toContain('p. 7 · Fig 4b')
    expect(chips('b [Page 2, Table 1]')).toContain('p. 2 · Table 1')
  })
})
