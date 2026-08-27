import type { AppProps } from 'next/app';
import Head from 'next/head';
import '../styles/globals.css';
import { AuthProvider } from '../lib/auth/auth-context';
import Sidebar from '../components/Sidebar';

export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        <title>Research Scanner | Schwarz Intelligence</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Newsreader:ital,opsz,wght@0,6..72,400..700;1,6..72,400..700&display=swap" rel="stylesheet" />
      </Head>
      <AuthProvider>
        <div className="flex min-h-screen bg-white text-slate-900 font-sans antialiased selection:bg-teal-500 selection:text-white">
          <Sidebar />
          <main className="flex-1 min-w-0 bg-white min-h-screen overflow-y-auto">
            <Component {...pageProps} />
          </main>
        </div>
      </AuthProvider>
    </>
  );
}
