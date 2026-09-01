import '@/styles/tailwind.css'
import type { Metadata } from 'next'
import { Toaster } from 'sonner'
import localFont from 'next/font/local'

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

// Runtime env (not NEXT_PUBLIC_*): the image is built once and deployed anywhere.
const siteUrl = process.env.SITE_URL ?? process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'
const siteName = 'Research Intelligence'
const siteDescription =
  'Research Intelligence reads new papers as they land, scores them across the dimensions that matter, and surfaces what deserves attention.'

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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${switzer.variable} ${plexMono.variable}`}>
      <body className="text-foreground antialiased">
        {children}
        {/* Un-anchored background outcomes only (first consumers: batch 4).
            Anchored errors — forms, turns, dialogs — never toast. */}
        <Toaster toastOptions={{ style: { borderRadius: '2px' } }} />
      </body>
    </html>
  )
}
