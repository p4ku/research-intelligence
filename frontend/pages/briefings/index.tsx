"use client";

import React from 'react';
import Link from 'next/link';
import { FileText, Download, Calendar, ArrowRight, CheckCircle2 } from 'lucide-react';

const mockBriefings = [
  {
    id: 'briefing-2026-w26',
    title: 'Weekly Executive Intelligence Brief: Week 26 (Physical AI & Generalist Manipulation)',
    date: 'July 3, 2026',
    summary: 'Key findings from 9 screened papers across arXiv and OpenAlex. Focus on zero-shot SKU teleoperation (Vela Robotics) and C2PA verifiable media credentials.',
    papersCount: 9,
    leadSignal: 85,
  },
  {
    id: 'briefing-2026-w25',
    title: 'Weekly Executive Intelligence Brief: Week 25 (Agentic Memory & Verifier Loops)',
    date: 'June 26, 2026',
    summary: 'Review of long-horizon agent architectures with selective store-retrieve-forget gating mechanisms and verifier-in-the-loop deterministic state machines.',
    papersCount: 7,
    leadSignal: 84,
  },
];

export default function BriefingsPage() {
  return (
    <div className="p-8 sm:p-10 max-w-6xl mx-auto">
      
      {/* Header */}
      <div className="flex items-center justify-between pb-6 border-b border-[#f0f0f0] mb-8">
        <div>
          <div className="flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-500 mb-1">
            <span className="text-teal-600 font-bold">■</span> EXECUTIVE SUMMARIES
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950">
            Briefings & Reports
          </h1>
        </div>
      </div>

      {/* Briefing Cards List */}
      <div className="space-y-5">
        {mockBriefings.map((briefing) => (
          <div
            key={briefing.id}
            className="bg-white border border-[#e5e7eb] rounded-xl p-6 hover:border-slate-300 transition-colors"
          >
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-3">
              <div>
                <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-1.5">
                  <Calendar className="w-3.5 h-3.5" />
                  <span>{briefing.date}</span>
                  <span>·</span>
                  <span className="text-teal-700 font-semibold">{briefing.papersCount} papers synthesized</span>
                </div>
                <h3 className="text-lg font-bold text-slate-950 hover:text-teal-700 transition-colors">
                  {briefing.title}
                </h3>
              </div>

              <div className="w-12 h-12 rounded-full border-2 border-teal-500 flex items-center justify-center font-extrabold text-sm text-slate-900 flex-shrink-0">
                {briefing.leadSignal}
              </div>
            </div>

            <p className="text-xs sm:text-sm text-slate-600 leading-relaxed mb-4">
              {briefing.summary}
            </p>

            <div className="flex items-center justify-between pt-3 border-t border-[#f1f5f9] text-xs">
              <span className="text-slate-400 font-mono">Status: Published</span>
              <button className="flex items-center gap-1.5 text-slate-700 hover:text-slate-900 font-semibold">
                <Download className="w-3.5 h-3.5" /> Download PDF Report
              </button>
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}
