import { Card } from '@/components/scanner-ui'
import Link from 'next/link'

/** Segment-scoped 404 inside the Studio shell. English by decision (operator surface). */
export default function NotFound() {
  return (
    <div className="mx-auto max-w-lg pt-16">
      <Card>
        <p className="text-foreground text-sm font-medium">We couldn&apos;t find that.</p>
        <p className="text-muted-foreground mt-1 text-sm">
          It may have been removed, or the link may be out of date.
        </p>
        <div className="mt-4">
          <Link
            href="/runs"
            className="bg-foreground text-background hover:bg-foreground/85 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors"
          >
            Back to Runs
          </Link>
        </div>
      </Card>
    </div>
  )
}
