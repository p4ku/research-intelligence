import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { CompletionModal } from './completion-modal'

describe('CompletionModal Component Rendering', () => {
  test('returns null when isOpen is false', () => {
    const html = renderToStaticMarkup(
      <CompletionModal
        isOpen={false}
        pipelineRunId="f0a80123-0000-4000-8000-000000000001"
        cohortId="c0a80123-0000-4000-8000-000000000001"
      />,
    )
    expect(html).toBe('')
  })

  test('renders completion modal dialog when isOpen is true', () => {
    const html = renderToStaticMarkup(
      <CompletionModal
        isOpen={true}
        pipelineRunId="f0a80123-0000-4000-8000-000000000001"
        cohortId="c0a80123-0000-4000-8000-000000000001"
      />,
    )

    expect(html).toContain('Audit Checkpoint Complete!')
    expect(html).toContain(
      'All sampled articles in this checkpoint cohort have been independently evaluated.',
    )
    expect(html).toContain('href="/runs/f0a80123-0000-4000-8000-000000000001"')
    expect(html).toContain('Monitor Pipeline Run →')
    expect(html).toContain('href="/audit-queue"')
    expect(html).toContain('Return to Audit Queue')
  })
})
