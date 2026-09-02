import { PageHeader } from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import clsx from 'clsx'
import {
  AskLayout,
  BODY_CLASS,
  ComposerFrame,
  ConsoleFrame,
  ConsoleNote,
  DOCK_WRAP,
  EMPTY_BODY_PAD,
  FIELD_CLASS,
  GREETING_WRAP,
  Greeting,
} from './console-frame'
import { HistoryRailSkeleton } from './history-rail'
import { PaperPickerSkeleton } from './paper-picker'

/**
 * The console before its data arrives: the real chrome (strip, greeting,
 * composer box) with bones only where the corpus and the history would show —
 * the picker rows under the composer and the session rows in the rail. Used
 * as the page's Suspense fallback and, under the header, as loading.tsx.
 */

/** The page's flex column is a fixed viewport height; the region must pass it down. */
const FILL = 'flex min-h-0 flex-1 flex-col'

export function AskConsoleSkeleton({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading the assistant')} className={FILL} innerClassName={FILL}>
      <AskLayout
        railLabel={t('Conversation history')}
        console={
          <ConsoleFrame
            label={t('Ask console')}
            eyebrow={t('Ask', 'console')}
            aside={<ConsoleNote>{t('No paper yet')}</ConsoleNote>}
          >
            <div className={clsx(BODY_CLASS, EMPTY_BODY_PAD)}>
              <div className={GREETING_WRAP}>
                <Greeting lead={t('Ask a paper.')} />
              </div>
              <div className={DOCK_WRAP}>
                <ComposerFrame
                  field={
                    <div className={FIELD_CLASS}>
                      <Bone.Text widths={['34ch']} />
                    </div>
                  }
                  footer={
                    <>
                      <span className="flex-1" />
                      <Bone.Block className="size-8" round />
                    </>
                  }
                />
                <PaperPickerSkeleton placement="below" />
              </div>
            </div>
          </ConsoleFrame>
        }
        rail={<HistoryRailSkeleton />}
        mobileTitle={t('History')}
        mobileCount={<Bone.Text widths={['11ch']} />}
        mobileList={null}
      />
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: the real header over the console skeleton. */
export function AskPageSkeleton({ t }: { t: T }) {
  return (
    <div className="flex h-[calc(100dvh-6.5rem)] flex-col gap-6 lg:h-[calc(100dvh-6rem)]">
      <div className="shrink-0">
        <PageHeader eyebrow={t('Assistant')} title={t('Ask Research Intelligence')} />
      </div>
      <AskConsoleSkeleton t={t} />
    </div>
  )
}
