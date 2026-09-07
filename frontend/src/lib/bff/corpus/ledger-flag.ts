/**
 * Whether this request has read the run ledger. Set by the runs service the
 * moment `listEverywhere` is called; read by the corpus snapshot to decide
 * that the probe costs nothing here and must not be skipped (./store.ts
 * `effectiveTrust`). Per request through React's `cache`, so a route
 * handler's flag is never a page's. Imports nothing of its own.
 */
import { cache } from 'react'

export const ledgerRequested = cache(() => ({ yes: false }))
