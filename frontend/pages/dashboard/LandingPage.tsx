"use client";

import React from 'react';
import { 
  Sparkles, 
  Globe, 
  Cpu, 
  Database, 
  Lock, 
  ArrowRight, 
  Activity 
} from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="min-h-[calc(100vh-65px)] bg-[#090d16] bg-[radial-gradient(circle_at_50%_15%,#1e1b4b_0%,#090d16_65%)] text-slate-100 flex flex-col items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="max-w-4xl w-full text-center">
        
        {/* Badge */}
        <div className="inline-flex items-center gap-2 bg-sky-500/10 border border-sky-500/25 rounded-full px-4 py-1.5 text-xs sm:text-sm font-semibold text-sky-400 mb-6">
          <Sparkles className="w-4 h-4" />
          Multi-Agent Systematic Literature Review & Intelligence Platform
        </div>

        {/* Title */}
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-tight mb-6 bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400 bg-clip-text text-transparent">
          Automated Academic Literature Review & Deep-Tech Scouting
        </h1>

        <p className="text-lg sm:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
          Ingest papers across ArXiv, OpenAlex, and Lens. Screen full-text PDFs with multimodal Gemini 3.7 Flash and extract validated intelligence matrices.
        </p>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4 mb-16">
          <a
            href="/login"
            className="inline-flex items-center gap-2.5 bg-sky-600 hover:bg-sky-500 text-white font-bold text-base px-8 py-3.5 rounded-xl shadow-xl shadow-sky-600/30 hover:shadow-sky-500/40 hover:-translate-y-0.5 active:translate-y-0 transition-all"
          >
            <Lock className="w-4 h-4" />
            Sign In to Workspaces
            <ArrowRight className="w-4 h-4" />
          </a>

          <a
            href="/status"
            className="inline-flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-700 font-semibold text-base px-6 py-3.5 rounded-xl transition-all"
          >
            <Activity className="w-4 h-4 text-emerald-400" />
            System Diagnostics
          </a>
        </div>

        {/* Feature Highlights Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-left">
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 hover:border-slate-700 transition-colors">
            <div className="w-10 h-10 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 mb-4">
              <Globe className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-100 mb-2">Multi-Source Ingestion</h3>
            <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
              Real-time scrapers for ArXiv, OpenAlex, and Lens with title, DOI, and arXiv ID deduplication across millions of papers.
            </p>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 hover:border-slate-700 transition-colors">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 mb-4">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-100 mb-2">Dual-Stage AI Screening</h3>
            <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
              Stage 1 Abstract Screening & Stage 2 Multimodal PDF evaluation using Google Gemini 3.7 Flash.
            </p>
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 hover:border-slate-700 transition-colors">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 mb-4">
              <Database className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-100 mb-2">Structured Extractions</h3>
            <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
              Schema-validated extraction into structured matrices with evidence quotes, confidence, and TRL metrics.
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}
