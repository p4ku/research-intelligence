"use client";

import React, { useEffect } from 'react';
import { useAuth } from '../../lib/auth/auth-context';
import { Crosshair } from 'lucide-react';

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      window.location.href = '/login';
    }
  }, [isLoading, isAuthenticated]);

  if (isLoading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3 text-slate-500">
        <div className="w-10 h-10 rounded-full border border-slate-900 flex items-center justify-center text-slate-900 animate-pulse">
          <Crosshair className="w-5 h-5 stroke-[2.2]" />
        </div>
        <div className="text-xs font-mono text-slate-400">
          Verifying session...
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
