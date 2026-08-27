"use client";

import React from 'react';
import { 
  Sparkles, 
  Lock, 
  ArrowRight, 
  Activity 
} from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="min-h-[calc(100vh-65px)] bg-[#090d16] bg-[radial-gradient(circle_at_50%_25%,#1e1b4b_0%,#090d16_65%)] text-slate-100 flex flex-col items-center justify-center px-4 py-16">
      <div className="max-w-2xl w-full text-center">
        
        {/* Stealth Icon */}
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-sky-600 to-sky-400 shadow-xl shadow-sky-500/20 mb-8">
          <Sparkles className="w-8 h-8 text-white" />
        </div>

        {/* Title */}
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight leading-tight mb-8 bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400 bg-clip-text text-transparent">
          Schwarz Research Intelligence
        </h1>

        {/* Minimal Action Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4">
          <a
            href="/login"
            className="inline-flex items-center gap-2.5 bg-sky-600 hover:bg-sky-500 text-white font-bold text-sm sm:text-base px-7 py-3 rounded-xl shadow-lg shadow-sky-600/25 hover:shadow-sky-500/35 hover:-translate-y-0.5 active:translate-y-0 transition-all"
          >
            <Lock className="w-4 h-4" />
            Sign In
            <ArrowRight className="w-4 h-4" />
          </a>

          <a
            href="/status"
            className="inline-flex items-center gap-2 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800 font-semibold text-sm sm:text-base px-6 py-3 rounded-xl transition-all"
          >
            <Activity className="w-4 h-4 text-emerald-400" />
            System Status
          </a>
        </div>

      </div>
    </div>
  );
}
