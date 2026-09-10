import { fmt, type T } from '@/lib/i18n'
import type { RiskAndAffiliation, RiskFlag } from '@/lib/papers/types'
import {
  ArrowUpRightIcon,
  BuildingLibraryIcon,
  CheckCircleIcon,
  CodeBracketIcon,
  EnvelopeIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  ShieldCheckIcon,
} from '@heroicons/react/16/solid'
import clsx from 'clsx'

export function normalizeFlagLabel(label: string, key?: string, t: T = (s) => s): string {
  const l = (label || '').trim().toLowerCase()
  const k = (key || '').trim().toLowerCase()
  if (
    l === 'gdpr sovereignty' ||
    l === 'gdpr soverignity' ||
    l === 'gdpr' ||
    k === 'gdpr' ||
    k === 'compliance_risks' ||
    k === 'compliance'
  ) {
    return t('Compliance Risks')
  }
  return label
}

const FLAG_ORDER: Record<string, number> = {
  schwarz_ecosystem: 1,
  schwarz: 1,
  competitor: 2,
  competitor_involvement: 2,
  compliance_risks: 3,
  compliance: 3,
  gdpr: 3,
  gdpr_sovereignty: 3,
}

export function getFlagSortOrder(flag: RiskFlag): number {
  const k = (flag.key || '').trim().toLowerCase()
  if (k in FLAG_ORDER) return FLAG_ORDER[k]
  const l = (flag.label || '').trim().toLowerCase()
  if (l.includes('schwarz') || l.includes('ecosystem')) return 1
  if (l.includes('competitor')) return 2
  if (l.includes('compliance') || l.includes('gdpr')) return 3
  return 99
}

// The verdicts this file writes itself (never backend prose), so they are
// translated; `t` defaults to identity for the unit tests that call the
// unpacker directly.
export function unpackFlag(
  flag: RiskFlag,
  t: T = (s) => s,
): { label: string; value: string; status: string } {
  let val = flag.value
  let status = flag.status
  const label = normalizeFlagLabel(flag.label, flag.key, t)

  // If already a clean string that isn't serialized JSON, return immediately
  if (typeof val === 'string' && !val.trim().startsWith('{')) {
    return { label, value: val, status }
  }

  let parsed: Record<string, unknown> | null = null
  if (flag.dict_value && typeof flag.dict_value === 'object') {
    parsed = flag.dict_value as Record<string, unknown>
  } else if (typeof val === 'object' && val !== null) {
    parsed = val as Record<string, unknown>
  } else if (typeof val === 'string') {
    const trimmed = val.trim()
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        parsed = JSON.parse(trimmed)
      } catch {
        // drop silent
      }
    }
  }

  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const rawStatus = parsed.status ?? parsed.value ?? parsed.risk ?? parsed.level
    const matches =
      parsed.matched_institutions ??
      parsed.matched_competitors ??
      parsed.matches ??
      parsed.institutions ??
      parsed.competitors ??
      parsed.details
    const items: string[] = []
    if (Array.isArray(matches)) {
      for (const m of matches) {
        if (
          m &&
          String(m).trim() !== '' &&
          String(m).trim() !== 'None' &&
          String(m).trim() !== 'null'
        ) {
          items.push(String(m).trim())
        }
      }
    } else if (
      matches &&
      String(matches).trim() !== '' &&
      String(matches).trim() !== 'None' &&
      String(matches).trim() !== 'null'
    ) {
      items.push(String(matches).trim())
    }

    const statStr = rawStatus !== undefined && rawStatus !== null ? String(rawStatus).trim() : ''
    const isPos =
      /^(yes|true|affiliated|high|present)$/i.test(statStr) ||
      (items.length > 0 && !/^(no|false|none|low|safe)$/i.test(statStr))
    const isNeg = /^(no|false|none|safe|low)$/i.test(statStr)

    if (isPos) {
      val = items.length > 0 ? `${t('YES')} (${items.join(', ')})` : t('YES')
      if (flag.key.includes('schwarz') || flag.key.includes('ecosystem')) status = 'highlight'
      else status = 'warn'
    } else if (isNeg) {
      val = flag.key.includes('competitor') ? t('None') : t('NO')
      status = 'safe'
    } else {
      val = items.length > 0 ? `${statStr} (${items.join(', ')})` : statStr || '—'
    }
  }

  return { label, value: typeof val === 'string' ? val : String(val ?? '—'), status }
}

export function RiskAffiliationFlagging({
  risk,
  className,
  t = (s) => s,
}: {
  risk?: RiskAndAffiliation | null
  className?: string
  t?: T
}) {
  if (!risk) return null

  const hasAffiliations = risk.affiliations && risk.affiliations.length > 0
  const hasContacts = risk.author_contacts && risk.author_contacts.length > 0
  const hasFunding = risk.funding_entities && risk.funding_entities.length > 0
  const hasLink = Boolean(risk.codebase_artifact_link)
  const hasFlags = risk.flags && risk.flags.length > 0

  if (!hasAffiliations && !hasContacts && !hasFunding && !hasLink && !hasFlags) {
    return null
  }

  const sortedFlags = hasFlags
    ? [...risk.flags].sort((a, b) => getFlagSortOrder(a) - getFlagSortOrder(b))
    : []

  return (
    <div
      data-row="risk-and-affiliation"
      className={clsx(
        'mt-3.5 space-y-2.5 rounded-lg border border-line-soft bg-zinc-50/50 p-3 text-xs dark:bg-zinc-900/40',
        className,
      )}
    >
      {/* 1. Affiliations, Contacts, and Artifact Links */}
      {(hasAffiliations || hasContacts || hasLink) && (
        <div className="flex max-w-full min-w-0 flex-wrap items-center gap-x-3 gap-y-1.5 text-zinc-600 dark:text-zinc-300">
          {hasAffiliations && (
            <div className="inline-flex max-w-full min-w-0 items-start gap-1.5 font-medium">
              <BuildingLibraryIcon
                aria-hidden="true"
                className="mt-0.5 size-3.5 shrink-0 text-zinc-400 dark:text-zinc-500"
              />
              <span className="[overflow-wrap:anywhere] break-words">
                {risk.affiliations.join(' · ')}
              </span>
            </div>
          )}

          {hasContacts && (
            <div className="flex max-w-full min-w-0 items-start gap-1.5 text-zinc-500 dark:text-zinc-400">
              <EnvelopeIcon
                aria-hidden="true"
                className="mt-0.5 size-3.5 shrink-0 text-zinc-400 dark:text-zinc-500"
              />
              <span className="min-w-0 flex-1 font-mono text-[11px] leading-relaxed [overflow-wrap:anywhere] break-words">
                {risk.author_contacts.map((contact, i) => (
                  <span key={contact} className="inline">
                    {i > 0 && <span className="mr-1 text-zinc-400">, </span>}
                    {contact.includes('@') ? (
                      <a
                        href={`mailto:${contact}`}
                        className="break-all hover:text-accent hover:underline"
                        title={fmt(t('Email {contact}'), { contact })}
                      >
                        {contact}
                      </a>
                    ) : (
                      contact
                    )}
                  </span>
                ))}
              </span>
            </div>
          )}

          {hasLink && (
            <a
              href={risk.codebase_artifact_link!}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium text-blue-600 hover:underline dark:text-blue-400"
              title={t('View codebase or artifact')}
            >
              <CodeBracketIcon aria-hidden="true" className="size-3.5" />
              <span>{t('Artifact Repository')}</span>
              <ArrowUpRightIcon aria-hidden="true" className="size-3" />
            </a>
          )}
        </div>
      )}

      {/* 2. Funding Entities */}
      {hasFunding && (
        <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">{t('Funding: ')}</span>
          {risk.funding_entities.join('; ')}
        </div>
      )}

      {/* 3. Risk and Ecosystem Badges / Flags */}
      {sortedFlags.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          {sortedFlags.map((rawFlag) => {
            const flag = unpackFlag(rawFlag, t)
            const isSafe = flag.status === 'safe'
            const isWarn = flag.status === 'warn'
            const isHighlight = flag.status === 'highlight'

            return (
              <span
                key={rawFlag.key}
                className={clsx(
                  'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium tracking-tight',
                  isSafe &&
                    'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-600/20 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-500/30',
                  isWarn &&
                    'bg-amber-50 text-amber-800 ring-1 ring-amber-600/20 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-500/30',
                  isHighlight &&
                    'bg-sky-50 text-sky-700 ring-1 ring-sky-600/20 dark:bg-sky-950/40 dark:text-sky-300 dark:ring-sky-500/30',
                  !isSafe &&
                    !isWarn &&
                    !isHighlight &&
                    'bg-zinc-100 text-zinc-600 ring-1 ring-zinc-500/15 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-700',
                )}
              >
                {isSafe && (
                  <CheckCircleIcon
                    aria-hidden="true"
                    className="size-3 shrink-0 text-emerald-500"
                  />
                )}
                {isWarn && (
                  <ExclamationTriangleIcon
                    aria-hidden="true"
                    className="size-3 shrink-0 text-amber-500"
                  />
                )}
                {isHighlight && (
                  <ShieldCheckIcon aria-hidden="true" className="size-3 shrink-0 text-sky-500" />
                )}
                {!isSafe && !isWarn && !isHighlight && (
                  <InformationCircleIcon
                    aria-hidden="true"
                    className="size-3 shrink-0 text-zinc-400"
                  />
                )}
                <span>
                  <span className="font-semibold">{flag.label}:</span> {flag.value}
                </span>
              </span>
            )
          })}

          {typeof risk.risk_score === 'number' && (
            <span className="inline-flex items-center gap-1 rounded-md bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-700 ring-1 ring-zinc-500/15 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-700">
              <span className="font-semibold">{t('Risk Score:')}</span> {risk.risk_score}/100
              {risk.risk_score_assessment && (
                <span className="text-zinc-500 dark:text-zinc-400">
                  ({risk.risk_score_assessment})
                </span>
              )}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
