import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { Bone, Skeleton } from './skeleton'

describe('Bone', () => {
  test('Text repeats the fixed width pattern in order and fills whole line boxes', () => {
    const out = renderToStaticMarkup(<Bone.Text lines={4} />)
    const widths = [...out.matchAll(/width:([\d.]+%)/g)].map((m) => m[1])
    expect(widths).toEqual(['100%', '88%', '46%', '100%'])
    expect(out.match(/h-\[1lh\]/g)).toHaveLength(4)
  })

  test('Text takes explicit widths (ch for flex rows)', () => {
    expect(renderToStaticMarkup(<Bone.Text widths={['9ch']} />)).toContain('width:9ch')
  })

  test('Number reserves the digit width in ch', () => {
    expect(renderToStaticMarkup(<Bone.Number digits={4} />)).toContain('width:4ch')
  })

  test('Chip matches the 20px pill height', () => {
    expect(renderToStaticMarkup(<Bone.Chip width={104} />)).toContain('h-5')
  })

  test('bones never use animate-pulse — pulse means "running" in this app', () => {
    const out = renderToStaticMarkup(
      <Skeleton.Region status="Loading">
        <Bone.Text lines={2} />
        <Bone.Number />
        <Bone.Chip />
        <Bone.Block className="h-6 w-24" />
        <Bone.Dot />
        <Bone.Ring />
      </Skeleton.Region>,
    )
    expect(out).not.toContain('animate-pulse')
  })
})

describe('Skeleton.Region', () => {
  const out = renderToStaticMarkup(
    <Skeleton.Region status="Loading the papers" data-pane="skeleton">
      <Bone.Text />
    </Skeleton.Region>,
  )

  test('carries the scan-sweep hook, busy state, and passthrough props', () => {
    expect(out).toContain('data-skeleton')
    expect(out).toContain('aria-busy="true"')
    expect(out).toContain('data-pane="skeleton"')
  })

  test('announces exactly one status and hides the bones from AT', () => {
    expect(out.match(/role="status"/g)).toHaveLength(1)
    expect(out).toContain('Loading the papers')
    expect(out).toContain('aria-hidden="true"')
  })
})
