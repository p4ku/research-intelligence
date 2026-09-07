'use client'

import { usePathname, useRouter } from 'next/navigation'
import { createContext, useCallback, useContext, useMemo } from 'react'
import {
  ALL_ON,
  decodeFeaturesCookie,
  encodeFeaturesCookie,
  featureOwning,
  FEATURES_COOKIE,
  type FeatureKey,
  type Features,
} from './features'

/**
 * The client's view of the demo flags. Seeded from the cookie by the shell
 * (never read from document.cookie here, so server and client agree within
 * a render), toggled from the account menu, and re-seeded on every server
 * render — the same shape as LanguageProvider.
 *
 * Without a provider (Studio's page tree, unit renders) everything is on.
 */

interface FeaturesValue {
  features: Features
  setFeature: (key: FeatureKey, on: boolean) => void
}

/**
 * Exported for tests only. `FeaturesProvider` calls useRouter()/usePathname(),
 * which throw outside a mounted App Router, so a unit render that needs a
 * flag-off subtree (src/components/paper-card.test.tsx) provides the context
 * directly rather than mocking next/navigation.
 */
export const FeaturesContext = createContext<FeaturesValue>({
  features: ALL_ON,
  setFeature: () => {},
})

export function FeaturesProvider({
  features,
  children,
}: {
  features: Features
  children: React.ReactNode
}) {
  const router = useRouter()
  const pathname = usePathname()
  // The shell hands in a fresh object every render; keying on the encoded
  // string keeps the context value stable across refreshes that change nothing.
  const encoded = encodeFeaturesCookie(features)

  const setFeature = useCallback(
    (key: FeatureKey, on: boolean) => {
      const next = { ...decodeFeaturesCookie(encoded), [key]: on }
      // Same attributes as the language cookie (src/lib/i18n-client.tsx).
      document.cookie = `${FEATURES_COOKIE}=${encodeFeaturesCookie(next)};path=/;max-age=31536000;samesite=lax`
      // Turning off the flag that owns the current route would 404 it under
      // the reader: one hard navigation Home instead of a refresh-then-replace.
      if (!on && featureOwning(pathname) === key) {
        // A full load on purpose: router.push() would keep this shell's
        // server-rendered nav, and push()+refresh() in one tick races the
        // 404 the refresh would now produce for the route we are leaving.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign('/dashboard')
        return
      }
      router.refresh()
    },
    [encoded, pathname, router],
  )

  const value = useMemo(
    () => ({ features: decodeFeaturesCookie(encoded), setFeature }),
    [encoded, setFeature],
  )
  return <FeaturesContext.Provider value={value}>{children}</FeaturesContext.Provider>
}

export function useFeatures(): Features {
  return useContext(FeaturesContext).features
}

export function useSetFeature(): FeaturesValue['setFeature'] {
  return useContext(FeaturesContext).setFeature
}
