"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { 
  Star, 
  ArrowLeft, 
  Send, 
  CheckCircle2, 
  ExternalLink 
} from 'lucide-react';

export default function PaperDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [starred, setStarred] = useState(true);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{ sender: 'user' | 'assistant'; text: string }>>([]);

  const handleSendChat = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMsg = chatInput;
    setChatMessages(prev => [...prev, { sender: 'user', text: userMsg }]);
    setChatInput('');

    setTimeout(() => {
      setChatMessages(prev => [
        ...prev,
        {
          sender: 'assistant',
          text: `Based on the paper "Every SKU, One Policy", the 91% first-attempt success rate was achieved by collecting 10,000 teleoperated hours across diverse SKU categories including deformable and transparent items.`
        }
      ]);
    }, 600);
  };

  return (
    <div className="p-8 sm:p-10 max-w-7xl mx-auto">
      
      {/* Breadcrumbs */}
      <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mb-4 truncate">
        <Link href="/papers" className="hover:text-slate-700">PAPERS</Link> / EVERY SKU, ONE POLICY: A GENERALIST VISION-LANGUAGE-ACTION MODEL FROM 10,000 HOURS OF WAREHOUSE TELEOPERATION
      </div>

      {/* Paper Header */}
      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-6 pb-6 border-b border-[#f0f0f0] mb-8">
        <div className="flex-1">
          <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-2">
            <span className="text-orange-600 font-semibold">● Physical AI</span>
            <span>·</span>
            <span>arXiv · cs.RO</span>
            <span>·</span>
            <span>Jun 29, 2026</span>
          </div>

          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-950 leading-snug mb-3">
            Every SKU, One Policy: A Generalist Vision-Language-Action Model from 10,000 Hours of Warehouse Teleoperation
          </h1>

          <div className="text-xs text-slate-500 font-medium">
            I. Novotná, G. Ferreira, Y. Tanaka, W. Krause · <strong className="text-slate-800">Vela Robotics</strong>
          </div>
        </div>

        {/* Score and Actions */}
        <div className="flex items-center gap-4 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-14 h-14 rounded-full border-4 border-teal-500 flex items-center justify-center font-extrabold text-xl text-slate-900">
              85
            </div>
            <div>
              <div className="text-[11px] font-mono text-slate-400 uppercase font-bold">Signal Score</div>
              <div className="text-xs font-bold text-teal-700">Strong signal</div>
            </div>
          </div>

          <button
            onClick={() => setStarred(!starred)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-semibold transition-colors ${
              starred
                ? 'bg-amber-50 border-amber-300 text-amber-800'
                : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50'
            }`}
          >
            <Star className={`w-3.5 h-3.5 ${starred ? 'fill-amber-500 text-amber-500' : 'text-slate-400'}`} />
            {starred ? 'Starred' : 'Star'}
          </button>
        </div>
      </div>

      {/* Main Split Body */}
      <div className="flex flex-col lg:flex-row gap-8">
        
        {/* Left 65% Column: Paper Insights & Deep Data */}
        <div className="flex-1 space-y-6">
          
          {/* THE ONE-LINER */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-6">
            <div className="text-[11px] font-mono uppercase font-bold text-teal-700 tracking-wider mb-2">
              ■ The One-Liner
            </div>
            <p className="text-sm font-semibold text-slate-900 leading-relaxed">
              One policy, trained on real warehouse teleop, picks unseen SKUs at 91% first-attempt success — at production cycle times, in live facilities.
            </p>
          </div>

          {/* WHY IT MATTERS */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-6">
            <div className="text-[11px] font-mono uppercase font-bold text-teal-700 tracking-wider mb-2">
              ■ Why It Matters
            </div>
            <p className="text-xs sm:text-sm text-slate-700 leading-relaxed">
              Mixed-SKU picking is the task that has kept distribution centers dependent on human hands, and this is the first generalist result evaluated inside running facilities rather than a lab cell. The strategic kicker: the moat here is not the architecture, it is the teleoperation corpus — which means whoever operates the most varied physical environments holds the scarce asset.
            </p>
          </div>

          {/* Key Stat Cards (3 Columns) */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-white border border-[#e5e7eb] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400 font-bold mb-2">
                Strategic Relevance
              </div>
              <div className="flex items-baseline gap-1 mb-1">
                <span className="text-2xl font-extrabold text-teal-700">88</span>
                <span className="text-xs text-slate-400 font-mono">/ 100</span>
              </div>
              <div className="text-[11px] text-slate-500">
                Schwarz business focus fit
              </div>
            </div>

            <div className="bg-white border border-[#e5e7eb] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400 font-bold mb-2">
                Readiness
              </div>
              <div className="text-sm font-bold text-slate-900 mb-1">
                TRL 6 <span className="text-xs font-normal text-slate-500">· Development</span>
              </div>
              <div className="text-[11px] text-slate-500">
                EU Horizon Annex G
              </div>
            </div>

            <div className="bg-white border border-[#e5e7eb] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400 font-bold mb-2">
                Reproducibility
              </div>
              <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 mb-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Code released · 1,120
              </div>
              <div className="text-[11px] text-slate-500">
                Code & artifacts
              </div>
            </div>
          </div>

          {/* Dimension Breakdown & Radar Profile Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            {/* Insight Dimensions Table */}
            <div className="bg-white border border-[#e5e7eb] rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="text-[11px] font-mono uppercase font-bold text-teal-700 tracking-wider">
                  ■ Insight Dimensions
                </div>
                <span className="text-[10px] font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-600">
                  TRL 6 · Development
                </span>
              </div>

              <div className="space-y-3.5 text-xs">
                <div className="border-b border-[#f1f5f9] pb-2">
                  <div className="flex justify-between font-semibold text-slate-900 mb-0.5">
                    <span>Novelty</span>
                    <span className="text-teal-700 font-bold">84</span>
                  </div>
                  <p className="text-[11px] text-slate-500">First VLA generalist trained end-to-end on live-facility teleop.</p>
                </div>

                <div className="border-b border-[#f1f5f9] pb-2">
                  <div className="flex justify-between font-semibold text-slate-900 mb-0.5">
                    <span>Significance</span>
                    <span className="text-teal-700 font-bold">90</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Unseen-SKU grasping at production speed unlocks largest DC task.</p>
                </div>

                <div className="border-b border-[#f1f5f9] pb-2">
                  <div className="flex justify-between font-semibold text-slate-900 mb-0.5">
                    <span>Rigour</span>
                    <span className="text-teal-700 font-bold">81</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Large-scale real-world eval with per-category breakdowns.</p>
                </div>

                <div className="border-b border-[#f1f5f9] pb-2">
                  <div className="flex justify-between font-semibold text-slate-900 mb-0.5">
                    <span>TRL</span>
                    <span className="text-teal-700 font-bold">6/9</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Evaluated in three live distribution centers at production takt.</p>
                </div>

                <div>
                  <div className="flex justify-between font-semibold text-slate-900 mb-0.5">
                    <span>Schwarz fit</span>
                    <span className="text-teal-700 font-bold">88</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Grocery-logistics setting maps one-to-one onto retail DC operations.</p>
                </div>
              </div>
            </div>

            {/* Profile Radar / Metrics Chart */}
            <div className="bg-white border border-[#e5e7eb] rounded-xl p-6 flex flex-col justify-between">
              <div>
                <div className="text-[11px] font-mono uppercase font-bold text-teal-700 tracking-wider mb-4">
                  ■ Profile
                </div>

                {/* Radar Pentagon Canvas Representation */}
                <div className="h-44 flex items-center justify-center relative">
                  <svg viewBox="0 0 200 200" className="w-full h-full max-w-[180px]">
                    {/* Background Grid Rings */}
                    <polygon points="100,20 180,75 150,165 50,165 20,75" fill="none" stroke="#f1f5f9" strokeWidth="1.5" />
                    <polygon points="100,45 155,85 135,145 65,145 45,85" fill="none" stroke="#e2e8f0" strokeWidth="1" />
                    
                    {/* Data Polygon */}
                    <polygon points="100,30 165,80 140,150 70,140 40,80" fill="rgba(20, 184, 166, 0.15)" stroke="#0d9488" strokeWidth="2" />
                    
                    {/* Labels */}
                    <text x="100" y="14" textAnchor="middle" fontSize="8" fill="#64748b" fontFamily="sans-serif">Novelty</text>
                    <text x="185" y="80" textAnchor="start" fontSize="8" fill="#64748b" fontFamily="sans-serif">Significance</text>
                    <text x="155" y="180" textAnchor="middle" fontSize="8" fill="#64748b" fontFamily="sans-serif">Rigour</text>
                    <text x="45" y="180" textAnchor="middle" fontSize="8" fill="#64748b" fontFamily="sans-serif">Schwarz fit</text>
                    <text x="10" y="80" textAnchor="end" fontSize="8" fill="#64748b" fontFamily="sans-serif">TRL</text>
                  </svg>
                </div>
              </div>

              {/* Citations & Repos */}
              <div className="pt-4 border-t border-[#f1f5f9] grid grid-cols-2 gap-4 text-xs font-mono">
                <div>
                  <span className="text-slate-400 block text-[10px]">Citations</span>
                  <span className="font-bold text-slate-900 text-sm">17</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Repo stars</span>
                  <span className="font-bold text-slate-900 text-sm">1,120</span>
                </div>
              </div>
            </div>

          </div>

          {/* ABSTRACT */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-6">
            <div className="text-[11px] font-mono uppercase font-bold text-teal-700 tracking-wider mb-2">
              ■ Abstract
            </div>
            <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
              We train a single vision-language-action policy on 10,000 hours of teleoperated manipulation collected in three live distribution centers, spanning 41,000 unique SKUs. The resulting generalist grasps items unseen during training — including deformables, shrink-wrapped multipacks, and glass — with 91% first-attempt success at production cycle times, and accepts natural-language task specifications without fine-tuning.
            </p>
          </div>

        </div>

        {/* Right 35% Column: ASK THIS PAPER Assistant */}
        <div className="w-full lg:w-96 flex-shrink-0">
          <div className="bg-white border border-[#e5e7eb] rounded-xl flex flex-col h-[680px] sticky top-8 shadow-sm">
            
            {/* Header */}
            <div className="p-4 border-b border-[#f1f5f9]">
              <div className="flex items-center gap-2 text-[11px] font-mono font-bold uppercase tracking-wider text-slate-900">
                <span className="text-orange-600">●</span> Ask This Paper
              </div>
              <p className="text-[11px] text-slate-400 mt-1 leading-snug">
                Questions here are answered from this paper alone.
              </p>
            </div>

            {/* Chat message stream */}
            <div className="flex-1 p-4 overflow-y-auto space-y-3">
              {chatMessages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-4 text-slate-400 text-xs">
                  <p>Ask any question regarding methodology, dataset, TRL validation, or deployment results.</p>
                </div>
              ) : (
                chatMessages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg text-xs leading-relaxed ${
                      msg.sender === 'user'
                        ? 'bg-slate-100 text-slate-900 ml-4 font-medium'
                        : 'bg-teal-50/70 border border-teal-100 text-slate-800 mr-4'
                    }`}
                  >
                    {msg.text}
                  </div>
                ))
              )}
            </div>

            {/* Input Form */}
            <form onSubmit={handleSendChat} className="p-3 border-t border-[#f0f0f0]">
              <div className="relative">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Ask about this paper..."
                  className="w-full bg-[#f8f9fa] border border-[#e5e7eb] rounded-lg px-3 py-2 pr-9 text-xs text-slate-900 placeholder:text-slate-400 outline-none focus:bg-white focus:border-slate-400"
                />
                <button
                  type="submit"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-teal-600 transition-colors p-1"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </form>

          </div>
        </div>

      </div>

    </div>
  );
}
