import React from 'react';
import { AuthProvider } from '../lib/auth/auth-context';
import Navbar from '../components/Navbar';

export const metadata = {
  title: 'Schwarz Research Intelligence',
  description: 'AI-Powered Systematic Literature Review & Deep-Tech Scouting Platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, -apple-system, sans-serif', backgroundColor: '#090d16', color: '#f8fafc' }}>
        <AuthProvider>
          <Navbar />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
