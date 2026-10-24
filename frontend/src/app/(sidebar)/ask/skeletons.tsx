import { Bone, Skeleton } from '@/components/skeleton'
import { APP_NAME } from '@/lib/config'
import { fmt, type T } from '@/lib/i18n'
import { PlusIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import {
  AskCanvas,
  BODY_CLASS,
  ComposerFrame,
  DOCK_WRAP,
  EMPTY_BODY,
  FIELD_CLASS,
  GREETING_WRAP,
  Greeting,
  ICON_BUTTON,
  PanelRightIcon,
  TopBar,
} from './console-frame'

/**
 * The canvas before its data arrives: the real chrome (top bar, greeting,
 * composer box) with a bone only where the typed question would go. The
 * sidecar is closed by default, so there is nothing to bone there — the
 * corpus behind the picker is not on screen either until the reader asks
 * for it. Used as the page's Suspense fallback and as loading.tsx.
 */

/** The page's flex column is a fixed viewport height; the region must pass it down. */
const FILL = 'flex min-h-0 flex-1 flex-col'

export function AskConsoleSkeleton({ t }: { t: T }) {
  return (
    <Skeleton.Region status={t('Loading the assistant')} className={FILL} innerClassName={FILL}>
      <AskCanvas
        label={t('Ask console')}
        top={
          <TopBar
            title={t('New chat')}
            actions={
              <>
                <span className={ICON_BUTTON}>
                  <PanelRightIcon className="size-[18px]" />
                </span>
                <span className={ICON_BUTTON}>
                  <Bone.Block className="size-4" />
                </span>
              </>
            }
          />
        }
      >
        <div className={clsx(BODY_CLASS, EMPTY_BODY)}>
          <div className={GREETING_WRAP}>
            <Greeting lead={t('What should we look into?')} />
          </div>
          <div className={DOCK_WRAP}>
            <ComposerFrame
              leading={
                <span className={ICON_BUTTON}>
                  <PlusIcon className="size-4" />
                </span>
              }
              field={
                <div className={FIELD_CLASS}>
                  <Bone.Text widths={['22ch']} />
                </div>
              }
              trailing={<Bone.Block className="size-8" />}
            />
          </div>
        </div>
      </AskCanvas>
    </Skeleton.Region>
  )
}

/** The loading.tsx shell: the canvas skeleton at the page's own height. */
export function AskPageSkeleton({ t }: { t: T }) {
  return (
    <div data-canvas className="flex min-h-0 flex-1 flex-col">
      <h1 className="sr-only">{fmt(t('Ask {appName}'), { appName: APP_NAME })}</h1>
      <AskConsoleSkeleton t={t} />
    </div>
  )
}
