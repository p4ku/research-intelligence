import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { AnswerMarkdown } from './answer-markdown'

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

  test('leaves bare reference markers and citation markers as text', () => {
    const src = 'See [1] and [Page 7, Fig 4b, box_2d: [1, 2], quote: "x"].'
    const out = html(src)
    expect(out).not.toContain('<a ')
    expect(out).toContain('[1]')
    expect(out).toContain('box_2d: [1, 2]')
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
