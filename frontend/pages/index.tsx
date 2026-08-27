import React from 'react';
import { useAuth } from '../lib/auth/auth-context';
import { DashboardPage, LandingPage } from './dashboard';
import { Sparkles } from 'lucide-react';

export default function HomePage() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-[80vh] flex flex-col items-center justify-center gap-5 text-slate-400">
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-sky-600 to-sky-400 flex items-center justify-center animate-pulse">
          <Sparkles className="w-6 h-6 text-white" />
        </div>
        <div className="text-sm font-medium">
          Loading session...
        </div>
      </div>
    );
  }

  return isAuthenticated ? <DashboardPage /> : <LandingPage />;
}
