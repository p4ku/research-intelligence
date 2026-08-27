"use client";

import React from 'react';
import { useAuth } from '../lib/auth/auth-context';
import LandingPage from './dashboard/LandingPage';
import DashboardPage from './dashboard/DashboardPage';

export default function HomePage() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center bg-white">
        <div className="w-8 h-8 rounded-full border-2 border-slate-900 border-t-transparent animate-spin" />
      </div>
    );
  }

  return isAuthenticated ? <DashboardPage /> : <LandingPage />;
}
