import { getLang } from '@/lib/i18n-server'
import '@/styles/tailwind.css'
import type { Metadata } from 'next'
import localFont from 'next/font/local'
import { Toaster } from 'sonner'

// Self-hosted: no third-party font CDNs from a German corporate deployment.
const switzer = localFont({
  src: '../fonts/switzer-variable.woff2',
  variable: '--font-switzer',
  weight: '100 900',
  display: 'swap',
})
const plexMono = localFont({
  src: [
    { path: '../fonts/plex-400.woff2', weight: '400' },
    { path: '../fonts/plex-500.woff2', weight: '500' },
    { path: '../fonts/plex-600.woff2', weight: '600' },
  ],
  variable: '--font-plex-mono',
  display: 'swap',
})

import { APP_DESCRIPTION, APP_NAME } from '@/lib/config'

// Runtime env: the image is built once and deployed anywhere.
const siteUrl = process.env.SITE_URL ?? process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'
const siteName = APP_NAME
const siteDescription = APP_DESCRIPTION

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    template: `%s · ${siteName}`,
    default: siteName,
  },
  description: siteDescription,
  openGraph: {
    type: 'website',
    siteName,
    title: siteName,
    description: siteDescription,
    url: siteUrl,
  },
  twitter: {
    card: 'summary_large_image',
    title: siteName,
    description: siteDescription,
  },
  // Internal tool — keep it out of search indexes.
  robots: { index: false, follow: false },
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  // The document language follows the UI language, so screen readers,
  // hyphenation and spellcheck get German when the chrome is German.
  const lang = await getLang()
  return (
    <html lang={lang} className={`${switzer.variable} ${plexMono.variable}`}>
      <body className="text-foreground antialiased">
        {children}
        {/* Un-anchored background outcomes only (first consumers: batch 4).
            Anchored errors — forms, turns, dialogs — never toast. */}
        <Toaster toastOptions={{ style: { borderRadius: '2px' } }} />
      </body>
    </html>
  )
}
