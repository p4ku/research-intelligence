'use client'

import { Card } from '@/components/scanner-ui'
import { useT } from '@/lib/i18n-client'

export default function PapersError({ error, reset }: { error: Error; reset: () => void }) {
  const t = useT()
  return (
    <Card>
      <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
        {t('Something went wrong loading papers.')}
      </p>
      <p className="mt-1 font-mono text-xs text-zinc-500 dark:text-zinc-400">{error.message}</p>
      <button
        type="button"
        onClick={reset}
        className="mt-4 rounded-md bg-zinc-950 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-200"
      >
        {t('Retry')}
      </button>
    </Card>
  )
}
