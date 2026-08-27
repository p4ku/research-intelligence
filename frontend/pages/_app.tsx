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
      </Head>
      <div className="min-h-screen bg-[#090d16] text-slate-100 antialiased selection:bg-sky-500 selection:text-white">
        <AuthProvider>
          <Navbar />
          <main className="w-full">
            <Component {...pageProps} />
          </main>
        </AuthProvider>
      </div>
    </>
  );
}
