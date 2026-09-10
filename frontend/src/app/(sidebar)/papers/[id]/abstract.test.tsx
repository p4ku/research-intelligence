import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { AbstractDisclosure } from './abstract'

const ABSTRACT =
  'We present a cryogenic control stack for superconducting qubits that reduces wiring heat load by 40% while preserving gate fidelity above 99.5% across 64 channels.'

describe('AbstractDisclosure', () => {
  test('renders collapsed on the server: one labelled control, the text mounted but inert', () => {
    const html = renderToStaticMarkup(<AbstractDisclosure text={ABSTRACT} />)
    expect(html).toMatch(/<button[^>]*aria-expanded="false"[^>]*>Abstract/)
    const panelId = html.match(/aria-controls="([^"]+)"/)?.[1]
    expect(panelId).toBeDefined()
    expect(html).toContain(`id="${panelId}"`)
    expect((html.match(/<button/g) ?? []).length).toBe(1)
    // Closed: zero rows and inert, so the text is neither seen nor reachable.
    expect(html).toContain('grid-rows-[0fr]')
    expect(html).toMatch(/<div[^>]*id="[^"]+"[^>]*inert=""/)
    // The authors' text is all there for the unfold — nothing is truncated.
    expect(html).toContain(ABSTRACT)
  })
})
