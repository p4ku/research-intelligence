import clsx from 'clsx'

// Research Intelligence brand mark — an aperture/eye of concentric arcs, evoking a
// scanner that watches the whole field. Uses currentColor so it inherits ink.
export function ScannerMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="1.5" opacity="0.25" />
      <circle cx="16" cy="16" r="9.5" stroke="currentColor" strokeWidth="1.5" opacity="0.45" />
      <circle cx="16" cy="16" r="4" fill="currentColor" />
      {/* scan ticks around the aperture */}
      <path d="M16 0.5V4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M16 28V31.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M31.5 16H28" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M4 16H0.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function ScannerWordmark({
  className,
  markClassName,
}: {
  className?: string
  markClassName?: string
}) {
  return (
    <span className={clsx('inline-flex items-center gap-2', className)}>
      <ScannerMark className={clsx('size-7', markClassName)} />
      <span className="text-sm font-semibold tracking-[0.14em] text-foreground uppercase">
        Research Intelligence
      </span>
    </span>
  )
}
