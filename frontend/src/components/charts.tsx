import clsx from 'clsx'

// Lightweight, dependency-free inline-SVG chart primitives.
//
// Colors follow the validated dataviz palette (docs/design.md). Categorical
// hues are passed in per-series (never cycled by rank). Chart chrome (axes,
// grid, labels) uses zinc utility classes so it adapts to light/dark; the
// data marks use the light-surface categorical steps, which are the app's
// default surface. See docs/design.md § "Charts and color".

// Souverän accent-derived sequential ramp (accent #00C3CD).
// Export keeps the seqBlue name so chart consumers don't change.
export const seqBlue = [
  '#e9f8f9', // near-zero
  '#c7eef1',
  '#93dfe4',
  '#57cfd7',
  '#00c3cd',
  '#0097a3',
  '#00707d',
  '#00434c',
]

/** Map a 0–100 value to a step of the sequential accent ramp. */
export function seqColor(value: number, max = 100): number | string {
  const t = Math.max(0, Math.min(1, value / max))
  const idx = Math.min(seqBlue.length - 1, Math.round(t * (seqBlue.length - 1)))
  return seqBlue[idx]
}

/* --------------------------------- Sparkline -------------------------------- */

export function Sparkline({
  data,
  width = 120,
  height = 32,
  color = 'var(--accent)',
  area = true,
  className,
  strokeWidth = 1.75,
}: {
  data: number[]
  width?: number
  height?: number
  color?: string
  area?: boolean
  className?: string
  strokeWidth?: number
}) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const span = max - min || 1
  const pad = strokeWidth
  const stepX = (width - pad * 2) / (data.length - 1)
  const points = data.map((v, i) => {
    const x = pad + i * stepX
    const y = pad + (height - pad * 2) * (1 - (v - min) / span)
    return [x, y] as const
  })
  const line = points
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(' ')
  const areaPath = `${line} L${points[points.length - 1][0].toFixed(1)} ${height} L${points[0][0].toFixed(1)} ${height} Z`
  const gid = `spark-${Math.round(min)}-${Math.round(max)}-${data.length}`

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={clsx('overflow-visible', className)}
      aria-hidden="true"
    >
      {area && (
        <>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.22" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={areaPath} fill={`url(#${gid})`} />
        </>
      )}
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="butt"
        strokeLinejoin="round"
      />
      <circle
        cx={points[points.length - 1][0]}
        cy={points[points.length - 1][1]}
        r={2.4}
        fill={color}
      />
    </svg>
  )
}

/* -------------------------------- Score meter ------------------------------- */

export function ScoreMeter({
  value,
  max = 100,
  color = 'var(--accent)',
  className,
}: {
  value: number
  max?: number
  color?: string
  className?: string
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div
      className={clsx('h-[3px] w-full overflow-hidden bg-line-soft', className)}
      role="meter"
      aria-valuenow={value}
      aria-valuemax={max}
    >
      <div className="h-full" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  )
}

/* -------------------------------- Radar chart ------------------------------- */

export function RadarChart({
  axes,
  size = 220,
  color = 'var(--accent)',
  className,
}: {
  axes: { label: string; value: number }[] // value 0–100
  size?: number
  color?: string
  className?: string
}) {
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 34
  const n = axes.length
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2
  const point = (i: number, radius: number) =>
    [cx + radius * Math.cos(angle(i)), cy + radius * Math.sin(angle(i))] as const

  const rings = [0.25, 0.5, 0.75, 1]
  const dataPts = axes.map((a, i) => point(i, r * Math.max(0.04, a.value / 100)))
  const dataPath =
    dataPts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ') +
    ' Z'

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className={clsx('overflow-visible', className)}
      width={size}
      height={size}
    >
      {rings.map((t) => (
        <polygon
          key={t}
          points={axes.map((_, i) => point(i, r * t).join(',')).join(' ')}
          fill="none"
          className="stroke-zinc-950/8 dark:stroke-white/10"
          strokeWidth="1"
        />
      ))}
      {axes.map((_, i) => {
        const [x, y] = point(i, r)
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={x}
            y2={y}
            className="stroke-zinc-950/8 dark:stroke-white/10"
            strokeWidth="1"
          />
        )
      })}
      <path
        d={dataPath}
        fill={color}
        fillOpacity={0.16}
        stroke={color}
        strokeWidth="2"
        strokeLinejoin="round"
      />
      {dataPts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={2.6} fill={color} />
      ))}
      {axes.map((a, i) => {
        const [x, y] = point(i, r + 18)
        return (
          <text
            key={a.label}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            className="fill-zinc-500 text-[10px] font-medium dark:fill-zinc-400"
          >
            {a.label}
          </text>
        )
      })}
    </svg>
  )
}

/* ------------------------------ Quadrant bubble ----------------------------- */

export interface BubbleDatum {
  id: string
  x: number // 0–xMax
  y: number // 0–yMax
  r: number // radius weight (raw, scaled internally)
  color: string
  label: string
}

export function QuadrantChart({
  data,
  xMax = 9,
  yMax = 100,
  xLabel = 'TRL',
  yLabel = 'Strategic relevance',
  quadrantLabels,
  midX = 5,
  midY = 50,
  height = 360,
  labelsOnHover = false,
  className,
}: {
  data: BubbleDatum[]
  xMax?: number
  yMax?: number
  xLabel?: string
  yLabel?: string
  quadrantLabels?: { tl: string; tr: string; bl: string; br: string }
  midX?: number
  midY?: number
  height?: number
  /** Show bubble labels only while the bubble is hovered (for dense plots). */
  labelsOnHover?: boolean
  className?: string
}) {
  const W = 640
  const H = height
  const m = { top: 20, right: 20, bottom: 40, left: 44 }
  const iw = W - m.left - m.right
  const ih = H - m.top - m.bottom
  const px = (x: number) => m.left + (x / xMax) * iw
  const py = (y: number) => m.top + ih - (y / yMax) * ih
  const maxR = Math.max(...data.map((d) => d.r), 1)
  const rr = (r: number) => 8 + (r / maxR) * 22

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={clsx('w-full', className)}
      role="img"
      aria-label={`${yLabel} versus ${xLabel}`}
    >
      {/* quadrant divider lines */}
      <line
        x1={px(midX)}
        y1={m.top}
        x2={px(midX)}
        y2={m.top + ih}
        className="stroke-zinc-950/8 dark:stroke-white/10"
        strokeDasharray="3 3"
      />
      <line
        x1={m.left}
        y1={py(midY)}
        x2={m.left + iw}
        y2={py(midY)}
        className="stroke-zinc-950/8 dark:stroke-white/10"
        strokeDasharray="3 3"
      />
      {/* axis frame */}
      <line
        x1={m.left}
        y1={m.top + ih}
        x2={m.left + iw}
        y2={m.top + ih}
        className="stroke-zinc-300 dark:stroke-zinc-700"
      />
      <line
        x1={m.left}
        y1={m.top}
        x2={m.left}
        y2={m.top + ih}
        className="stroke-zinc-300 dark:stroke-zinc-700"
      />

      {quadrantLabels && (
        <>
          <text
            x={m.left + 8}
            y={m.top + 16}
            className="fill-zinc-400 text-[10px] font-semibold tracking-wide uppercase"
          >
            {quadrantLabels.tl}
          </text>
          <text
            x={m.left + iw - 8}
            y={m.top + 16}
            textAnchor="end"
            className="fill-zinc-400 text-[10px] font-semibold tracking-wide uppercase"
          >
            {quadrantLabels.tr}
          </text>
          <text
            x={m.left + 8}
            y={m.top + ih - 8}
            className="fill-zinc-400 text-[10px] font-semibold tracking-wide uppercase"
          >
            {quadrantLabels.bl}
          </text>
          <text
            x={m.left + iw - 8}
            y={m.top + ih - 8}
            textAnchor="end"
            className="fill-zinc-400 text-[10px] font-semibold tracking-wide uppercase"
          >
            {quadrantLabels.br}
          </text>
        </>
      )}

      {data.map((d) => (
        <g key={d.id} className="group">
          <circle
            cx={px(d.x)}
            cy={py(d.y)}
            r={rr(d.r)}
            fill={d.color}
            fillOpacity={0.22}
            stroke={d.color}
            strokeWidth={1.5}
          />
          <text
            x={px(d.x)}
            y={py(d.y) + rr(d.r) + 11}
            textAnchor="middle"
            className={clsx(
              'fill-zinc-600 text-[9.5px] font-medium dark:fill-zinc-300',
              labelsOnHover &&
                'pointer-events-none opacity-0 transition-opacity group-hover:opacity-100',
            )}
          >
            {d.label}
          </text>
        </g>
      ))}

      <text
        x={m.left + iw / 2}
        y={H - 6}
        textAnchor="middle"
        className="fill-zinc-500 text-[11px] font-medium dark:fill-zinc-400"
      >
        {xLabel} →
      </text>
      <text
        x={12}
        y={m.top + ih / 2}
        textAnchor="middle"
        transform={`rotate(-90 12 ${m.top + ih / 2})`}
        className="fill-zinc-500 text-[11px] font-medium dark:fill-zinc-400"
      >
        {yLabel} →
      </text>
    </svg>
  )
}

/* --------------------------------- Heat grid -------------------------------- */

export function HeatGrid({
  rows,
  cols,
  values,
  format = (v) => String(Math.round(v)),
  className,
}: {
  rows: string[]
  cols: string[]
  values: number[][] // values[rowIdx][colIdx], 0–100
  format?: (v: number) => string
  className?: string
}) {
  return (
    <div className={clsx('overflow-x-auto', className)}>
      <table className="w-full border-separate border-spacing-0.5 text-sm">
        <thead>
          <tr>
            <th className="p-1.5" />
            {cols.map((c) => (
              <th
                key={c}
                className="p-1.5 text-center text-[11px] font-medium text-zinc-500 dark:text-zinc-400"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={r}>
              <th className="py-1.5 pr-3 text-right text-xs font-medium whitespace-nowrap text-zinc-600 dark:text-zinc-300">
                {r}
              </th>
              {cols.map((_, ci) => {
                const v = values[ri][ci]
                const bg = seqColor(v) as string
                // Cyan ramp stays light through mid steps; ink flips to white
                // only on the two darkest steps (#00707d, #00434c).
                const dark = v > 78
                return (
                  <td key={ci} className="p-0">
                    <div
                      className="flex h-11 items-center justify-center font-mono text-xs font-medium tabular-nums"
                      style={{ backgroundColor: bg, color: dark ? '#fff' : '#131311' }}
                      title={`${r} · ${cols[ci]}: ${format(v)}`}
                    >
                      {format(v)}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
