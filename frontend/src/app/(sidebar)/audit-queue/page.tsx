import { audit } from '@/lib/bff/audit/service'
import { AuditTable } from './audit-table'

export const dynamic = 'force-dynamic'

export default async function AuditQueuePage() {
  const queueItems = await audit.getMyQueue()

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-950 dark:text-white">
          Audit Queue
        </h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Systematic review checkpoint gates awaiting your verification.
        </p>
      </div>

      <AuditTable items={queueItems} />
    </div>
  )
}
