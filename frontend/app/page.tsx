"use client";

import React from 'react';
import { useAuth } from '../lib/auth/auth-context';
import { DashboardPage, LandingPage } from '../pages/dashboard';
import { Sparkles } from 'lucide-react';

export default function Home() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div style={{
        minHeight: '80vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '1.25rem',
        color: '#94a3b8',
      }}>
        <div style={{
          width: '48px',
          height: '48px',
          borderRadius: '12px',
          background: 'linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          animation: 'pulse 1.5s ease-in-out infinite',
        }}>
          <Sparkles size={24} color="#ffffff" />
        </div>
        <div style={{ fontSize: '0.95rem', fontWeight: '500' }}>
          Loading session...
        </div>
      </div>
    );
  }

  return isAuthenticated ? <DashboardPage /> : <LandingPage />;
}
