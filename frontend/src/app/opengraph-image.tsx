import { APP_NAME } from '@/lib/config'
import { ImageResponse } from 'next/og'

export const alt = APP_NAME
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default function OpengraphImage() {
  return new ImageResponse(
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: '80px',
        background: '#0b0b0a',
        color: '#f1f0ea',
        fontFamily: 'sans-serif',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <div style={{ display: 'flex', width: 16, height: 16, background: '#00c3cd' }} />
        <div
          style={{
            display: 'flex',
            fontSize: 32,
            fontWeight: 600,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
          }}
        >
          {APP_NAME}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div
          style={{
            display: 'flex',
            fontSize: 88,
            fontWeight: 700,
            lineHeight: 1.05,
            letterSpacing: '-0.022em',
          }}
        >
          The research field, watched continuously.
        </div>
        <div style={{ display: 'flex', fontSize: 34, opacity: 0.75, maxWidth: 900 }}>
          Reads new papers as they land, scores them across the dimensions that matter, and surfaces
          what deserves attention.
        </div>
      </div>
    </div>,
    size,
  )
}
