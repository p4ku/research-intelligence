import type { AppProps } from 'next/app';
import Head from 'next/head';
import '../styles/globals.css';
import { AuthProvider } from '../lib/auth/auth-context';
import Navbar from '../components/Navbar';

export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        <title>Schwarz Research Intelligence</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
      </Head>
      <AuthProvider>
        <div className="min-h-screen bg-white text-slate-900 font-sans antialiased flex flex-col selection:bg-teal-500 selection:text-white">
          <Navbar />
          <main className="flex-1 w-full bg-white">
            <Component {...pageProps} />
          </main>
        </div>
      </AuthProvider>
    </>
  );
}
