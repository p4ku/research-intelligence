import { assembleSearch } from '@/lib/bff/search/assemble'
import { fixtureSearchCorpus } from '@/lib/bff/search/fixtures'
import { tokenize } from '@/lib/search/match'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { SearchPanel } from './panel'
import { buildSections } from './rows'

const noop = () => {}
const t = (s: string) => s

function render(q: string, cursor = -1, pending = false) {
  const result = assembleSearch(fixtureSearchCorpus, { q, limit: 6 })
  const sections = buildSections(result, { q, recent: [], suggestions: [], error: false, t })
  return renderToStaticMarkup(
    <SearchPanel
      id="panel"
      sections={sections}
      cursor={cursor}
      pending={pending}
      tokens={tokenize(q)}
      showDomain
      onCursor={noop}
      onActivate={noop}
      onClearRecent={noop}
    />,
  )
}

describe('SearchPanel', () => {
  const out = render('agents', 0)

  test('is a listbox of options with the highlighted row selected', () => {
    expect(out).toContain('role="listbox"')
    // Two papers, the fixture domain (its name opens with "Agent…"), and Ask.
    expect(out.match(/role="option"/g)?.length).toBe(4)
    expect(out.match(/aria-selected="true"/g)?.length).toBe(1)
    expect(out).toContain('id="cs-paper-')
  })

  test('bolds the hit in the title and shows the score first', () => {
    expect(out).toContain('<mark class="bg-transparent font-semibold text-inherit">Agent</mark>')
    expect(out.indexOf('tabular-nums')).toBeLessThan(out.indexOf('<mark'))
  })

  test('names the domain, and the screening state only when not passed', () => {
    expect(out).toContain('Agentic AI Scan (fixture)')
    expect(out).toContain('Rejected')
    expect(out.match(/Rejected/g)?.length).toBe(1)
  })

  test('dims under data-pending, with no bones and no keycaps', () => {
    expect(render('agents', -1, true)).toContain('data-pending="true"')
    expect(out).not.toContain('data-pending="')
    expect(out).not.toContain('animate-pulse')
    expect(out).not.toContain('<kbd')
  })

  test('an id hit is one Open paper row linking to the paper', () => {
    const id = render('2608.01234')
    expect(id).toContain('Open paper')
    expect(id).toContain('href="/papers/00000000-0000-4000-8000-000000000041"')
  })

  test('a miss says so in plain words', () => {
    expect(render('perovskite')).toContain('No papers match “perovskite”.')
  })
})
