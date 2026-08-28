'use client'

import { useRouter } from 'next/navigation'
import { createContext, useCallback, useContext, useMemo } from 'react'
import { LANG_COOKIE, makeT, type Lang, type T } from './i18n'

const LanguageContext = createContext<{ lang: Lang; toggle: () => void }>({
  lang: 'en',
  toggle: () => {},
})

// Seeded from the cookie by the server layout, so client and server always
// agree on the language within a render. Toggling rewrites the cookie and
// refreshes so server components re-render in the new language too.
export function LanguageProvider({ lang, children }: { lang: Lang; children: React.ReactNode }) {
  const router = useRouter()
  const toggle = useCallback(() => {
    const next = lang === 'de' ? 'en' : 'de'
    document.cookie = `${LANG_COOKIE}=${next};path=/;max-age=31536000;samesite=lax`
    router.refresh()
  }, [lang, router])

  const value = useMemo(() => ({ lang, toggle }), [lang, toggle])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  return useContext(LanguageContext)
}

export function useT(): T {
  const { lang } = useLanguage()
  return useMemo(() => makeT(lang), [lang])
}
