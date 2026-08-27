"use client";

import React, { useState } from 'react';
import { Sliders, Save, Check, RefreshCw } from 'lucide-react';

export default function TuningPage() {
  const [weights, setWeights] = useState({
    fit: 40,
    novelty: 25,
    significance: 20,
    rigour: 15,
  });

  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="p-8 sm:p-10 max-w-5xl mx-auto">
      
      {/* Header */}
      <div className="flex items-center justify-between pb-6 border-b border-[#f0f0f0] mb-8">
        <div>
          <div className="flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-500 mb-1">
            <span className="text-teal-600 font-bold">■</span> SCORING CONFIGURATION
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950">
            Tuning & Criteria
          </h1>
        </div>

        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors cursor-pointer"
        >
          {saved ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Save className="w-3.5 h-3.5" />}
          {saved ? 'Saved' : 'Save Weights'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        {/* Signal Score Weights */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-6 space-y-6">
          <div className="text-xs font-mono uppercase font-bold text-slate-900">
            ■ Signal Score Formula Weights
          </div>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-xs font-semibold text-slate-900 mb-1">
                <span>Schwarz Fit Weight</span>
                <span className="text-teal-700 font-mono font-bold">{weights.fit}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={weights.fit}
                onChange={(e) => setWeights({ ...weights, fit: Number(e.target.value) })}
                className="w-full accent-teal-600 cursor-pointer"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs font-semibold text-slate-900 mb-1">
                <span>Novelty Weight</span>
                <span className="text-teal-700 font-mono font-bold">{weights.novelty}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={weights.novelty}
                onChange={(e) => setWeights({ ...weights, novelty: Number(e.target.value) })}
                className="w-full accent-teal-600 cursor-pointer"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs font-semibold text-slate-900 mb-1">
                <span>Significance Weight</span>
                <span className="text-teal-700 font-mono font-bold">{weights.significance}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={weights.significance}
                onChange={(e) => setWeights({ ...weights, significance: Number(e.target.value) })}
                className="w-full accent-teal-600 cursor-pointer"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs font-semibold text-slate-900 mb-1">
                <span>Rigour Weight</span>
                <span className="text-teal-700 font-mono font-bold">{weights.rigour}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={weights.rigour}
                onChange={(e) => setWeights({ ...weights, rigour: Number(e.target.value) })}
                className="w-full accent-teal-600 cursor-pointer"
              />
            </div>
          </div>
        </div>

        {/* Screening Criteria Prompts */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-6 space-y-4">
          <div className="text-xs font-mono uppercase font-bold text-slate-900">
            ■ Active Screening Rules
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Abstract Inclusion Criteria
            </label>
            <textarea
              defaultValue="Include peer-reviewed or preprint papers focusing on multi-agent architectures, warehouse robotics teleoperation, or C2PA provenance."
              rows={3}
              className="w-full bg-[#f8f9fa] border border-[#e5e7eb] rounded-lg p-3 text-xs text-slate-800 outline-none focus:bg-white focus:border-slate-400"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Full-Text Rejection Criteria
            </label>
            <textarea
              defaultValue="Reject theoretical review papers without reproducible benchmark results or empirical evaluations."
              rows={3}
              className="w-full bg-[#f8f9fa] border border-[#e5e7eb] rounded-lg p-3 text-xs text-slate-800 outline-none focus:bg-white focus:border-slate-400"
            />
          </div>
        </div>

      </div>

    </div>
  );
}
