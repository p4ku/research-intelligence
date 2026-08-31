import { appVersion, buildDetail } from '@/lib/version'
import clsx from 'clsx'

// The build that is running, one glance away under the wordmark: `v0.1.45`,
// with the commit and build time on hover. Bumps on every frontend change
// that reaches main (scripts/app-version.mjs), so "did the deploy go through"
// is answered by reading it.
export function VersionStamp({ className }: { className?: string }) {
  const detail = buildDetail()
  return (
    <span
      className={clsx(
        'font-mono text-[10px]/4 tracking-wide text-zinc-400 tabular-nums select-none dark:text-zinc-500',
        className,
      )}
      title={detail ? `Build ${detail}` : undefined}
    >
      v{appVersion}
    </span>
  )
}
