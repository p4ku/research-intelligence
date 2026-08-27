"use client";

import React from 'react';
import Link from 'next/link';
import { useAuth } from '../../lib/auth/auth-context';
import { 
  Crosshair, 
  ArrowRight, 
  Activity, 
  ShieldCheck, 
  ExternalLink,
  Layers
} from 'lucide-react';

export default function LandingPage() {
  const { isAuthenticated, user } = useAuth();

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-white flex flex-col justify-center items-center px-4 sm:px-6 lg:px-8 py-16">
      <div className="max-w-xl w-full text-center">
        
        {/* Stealth Brand Icon */}
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full border border-slate-900 bg-white mb-6 shadow-sm">
          <Crosshair className="w-8 h-8 text-slate-900 stroke-[2.2]" />
        </div>

        {/* Minimalist Header */}
        <div className="flex items-center justify-center gap-1.5 text-xs font-mono font-bold tracking-widest uppercase text-teal-700 mb-3">
          <span>■</span> SCHWARZ RESEARCH INTELLIGENCE
        </div>

        <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-950 tracking-tight leading-tight mb-4">
          Schwarz Research Intelligence
        </h1>

        <p className="text-sm text-slate-500 max-w-md mx-auto mb-8 leading-relaxed">
          Autonomous systematic literature review, deep-tech intelligence, and validated parameter extraction.
        </p>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          {isAuthenticated ? (
            <Link
              href="/dashboard"
              className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-bold text-white bg-slate-950 hover:bg-slate-800 active:scale-[0.99] shadow-sm transition-all"
            >
              <Layers className="w-4 h-4" />
              <span>Enter Workspaces</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          ) : (
            <Link
              href="/login"
              className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-bold text-white bg-slate-950 hover:bg-slate-800 active:scale-[0.99] shadow-sm transition-all"
            >
              <span>Sign In</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          )}

          <Link
            href="/status"
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-[#e5e7eb] shadow-sm transition-all"
          >
            <Activity className="w-4 h-4 text-teal-600" />
            <span>System Status</span>
          </Link>

          <a
            href="/admin/"
            target="_blank"
            rel="noreferrer"
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-[#e5e7eb] shadow-sm transition-all"
          >
            <ShieldCheck className="w-4 h-4 text-slate-400" />
            <span>Django Admin</span>
            <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
          </a>
        </div>

      </div>
    </div>
  );
}
