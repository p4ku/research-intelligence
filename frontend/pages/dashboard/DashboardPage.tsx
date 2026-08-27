"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '../../lib/auth/auth-context';
import { 
  Star, 
  ArrowRight, 
  Radio, 
  Briefcase, 
  Sparkles, 
  Zap, 
  Scale 
} from 'lucide-react';

interface PaperItem {
  id: string;
  score: number;
  sector: string;
  sectorColor: string;
  source: string;
  date: string;
  starred?: boolean;
  title: string;
  summary: string;
  trl: number;
  stage: string;
  novelty: number;
  significance: number;
  fit: number;
  rigour: number;
  lab: string;
}

const mockPapers: PaperItem[] = [
  {
    id: 'every-sku-one-policy',
    score: 85,
    sector: 'Physical AI',
    sectorColor: 'text-amber-600 bg-amber-500/10 border-amber-500/30',
    source: 'arXiv · cs.RO',
    date: 'Jun 29, 2026',
    starred: true,
    title: 'Every SKU, One Policy: A Generalist Vision-Language-Action Model from 10,000 Hours of Warehouse Teleoperation',
    summary: 'One policy, trained on real warehouse teleop, picks unseen SKUs at 91% first-attempt success — at production cycle times, in live facilities.',
    trl: 6,
    stage: 'Development',
    novelty: 84,
    significance: 90,
    fit: 88,
    rigour: 81,
    lab: 'Vela Robotics',
  },
  {
    id: 'consolidated-memory',
    score: 84,
    sector: 'Agentic AI',
    sectorColor: 'text-teal-600 bg-teal-500/10 border-teal-500/30',
    source: 'arXiv · cs.MA',
    date: 'Jun 28, 2026',
    starred: true,
    title: 'Consolidated Memory: Learned Retrieval and Forgetting for Long-Horizon Agents',
    summary: 'Agents get a real memory: learned store-retrieve-forget beats stuffing transcripts into context, 31% better at 1/6 the tokens.',
    trl: 4,
    stage: 'Development',
    novelty: 86,
    significance: 88,
    fit: 82,
    rigour: 84,
    lab: 'Meridian AI Lab',
  },
  {
    id: 'provenance-survives-internet',
    score: 82,
    sector: 'Provenance',
    sectorColor: 'text-indigo-600 bg-indigo-500/10 border-indigo-500/30',
    source: 'arXiv · cs.CR',
    date: 'Jul 1, 2026',
    starred: true,
    title: 'Provenance That Survives the Internet: Durable Content Credentials Through Re-Encoding, Cropping, and Platform Pipelines',
    summary: 'Content credentials that survive being posted: manifest + soft-binding watermark recovers provenance for 94% of assets after real platform pipelines, vs 31% today.',
    trl: 6,
    stage: 'Development',
    novelty: 78,
    significance: 87,
    fit: 89,
    rigour: 86,
    lab: 'TrustFabric',
  },
  {
    id: 'verifier-in-the-loop',
    score: 79,
    sector: 'Agentic AI',
    sectorColor: 'text-teal-600 bg-teal-500/10 border-teal-500/30',
    source: 'arXiv · cs.MA',
    date: 'Jun 24, 2026',
    starred: true,
    title: 'Verifier-in-the-Loop: Deterministic Control Flow for Multi-Agent Systems',
    summary: 'Treat agent fleets like workflow engines with a verifier gating every step — 44% fewer catastrophic failures than debate.',
    trl: 4,
    stage: 'Development',
    novelty: 72,
    significance: 84,
    fit: 85,
    rigour: 82,
    lab: 'Northwind Research',
  },
  {
    id: 'provenance-first-pipelines',
    score: 78,
    sector: 'Provenance',
    sectorColor: 'text-indigo-600 bg-indigo-500/10 border-indigo-500/30',
    source: 'arXiv · cs.CR',
    date: 'Jun 30, 2026',
    starred: false,
    title: 'Provenance-First Pipelines: End-to-End C2PA Signing for Generated Media',
    summary: 'Sign everything at generation time, verify at the gateway — C2PA provenance as pipeline infrastructure, deployed in a newsroom.',
    trl: 7,
    stage: 'Deployment',
    novelty: 63,
    significance: 85,
    fit: 80,
    rigour: 88,
    lab: 'TrustFabric',
  },
];

export default function DashboardPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'score' | 'fit' | 'novelty' | 'significance' | 'rigour'>('score');

  const greetingName = user?.first_name || user?.username || 'Johann';

  return (
    <div className="p-8 sm:p-10 max-w-6xl mx-auto">
      
      {/* Header Top Meta */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-6 border-b border-[#f0f0f0]">
        <div>
          <div className="flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-500 mb-1">
            <span className="text-teal-600 font-bold">■</span> TODAY · FRIDAY, JULY 3, 2026
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950">
            Good morning, {greetingName}
          </h1>
        </div>

        <div className="text-right">
          <div className="text-[11px] font-mono text-slate-500 mb-2">
            <span className="font-bold text-slate-900">24</span> identified → <span className="font-bold text-slate-900">9</span> screened → <span className="font-bold text-slate-900">4</span> deep-dived → <span className="font-bold text-slate-900">4</span> handed off · <span className="text-slate-400">week of 29 Jun</span>
          </div>
          <div className="flex items-center justify-end gap-2">
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold font-mono px-2 py-0.5 rounded bg-teal-600 text-white">
              ● Agentic AI / MAS
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold font-mono px-2 py-0.5 rounded bg-indigo-900 text-white">
              ● Digital Provenance & Trust
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold font-mono px-2 py-0.5 rounded bg-orange-600 text-white">
              ● Physical AI & Humanoids
            </span>
          </div>
        </div>
      </div>

      {/* HEADLINE STORIES Section */}
      <section className="my-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs font-bold font-mono tracking-wider uppercase text-slate-900 flex items-center gap-1.5">
            <span className="text-teal-600">■</span> Headline Stories
          </h2>
          <span className="text-xs text-slate-400 font-mono">1 lead · 3 more</span>
        </div>

        {/* Lead Story Card */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-6 sm:p-8 mb-6 hover:shadow-sm transition-shadow">
          <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
            <div className="flex-1">
              <div className="flex items-center gap-2 text-xs text-slate-500 font-mono mb-2">
                <span className="inline-flex items-center gap-1 text-orange-600 font-semibold">
                  ● Physical AI
                </span>
                <span>·</span>
                <span>Lead story</span>
              </div>

              <Link href="/papers/every-sku-one-policy" className="group">
                <h3 className="text-2xl sm:text-3xl font-extrabold text-slate-950 tracking-tight leading-snug mb-3 group-hover:text-teal-700 transition-colors">
                  The warehouse generalist has arrived — and it was trained in buildings like yours
                </h3>
              </Link>

              <p className="text-sm text-slate-600 leading-relaxed mb-4 max-w-3xl">
                Vela Robotics trained one vision-language-action policy on 10,000 hours of teleoperation from live distribution centers, and it picks unseen SKUs at 91% first-attempt success — at production takt, measured in running facilities. The strategic read: the moat is shifting from model architecture to manipulation data from varied real environments, which is an asset operators hold and labs do not. The engagement window has a clock on it — a European 3PL announced a pilot last week.
              </p>

              <div className="text-xs text-slate-400 font-mono">
                Every SKU, One Policy: A Generalist Vision-Language-Action Model from 10,000 Hours of Warehouse Teleoperation
              </div>
            </div>

            {/* Circular Signal Score */}
            <div className="flex flex-col items-center flex-shrink-0">
              <div className="w-20 h-20 rounded-full border-4 border-teal-500 flex items-center justify-center text-slate-900 font-extrabold text-2xl">
                85
              </div>
              <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold mt-1">
                Signal
              </span>
            </div>
          </div>
        </div>

        {/* 3 Sub-Headline Stories */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Sub 1 */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 hover:border-slate-300 transition-colors flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-xs text-slate-500 font-mono mb-2">
                <span className="text-indigo-600 font-semibold">● Provenance</span>
                <span className="font-bold text-slate-900">82</span>
              </div>
              <h4 className="text-base font-bold text-slate-950 leading-snug mb-2">
                Provenance that survives being posted
              </h4>
              <p className="text-xs text-slate-600 leading-relaxed">
                C2PA credentials die on first re-encode — until now. Pairing manifests with a robust soft-binding watermark recovers provenance for 94% of assets after real platform pipelines, versus 31% today. Article 50 compliance that holds up on the actual Internet.
              </p>
            </div>
          </div>

          {/* Sub 2 */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 hover:border-slate-300 transition-colors flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-xs text-slate-500 font-mono mb-2">
                <span className="text-teal-600 font-semibold">● Agentic AI</span>
                <span className="font-bold text-slate-900">84</span>
              </div>
              <h4 className="text-base font-bold text-slate-950 leading-snug mb-2">
                Agents finally get a memory worth the name
              </h4>
              <p className="text-xs text-slate-600 leading-relaxed">
                Learned store-retrieve-forget beats stuffing transcripts into context by 31% at a sixth of the tokens — and keeps the memory trend at the top of the board.
              </p>
            </div>
          </div>

          {/* Sub 3 */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 hover:border-slate-300 transition-colors flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-xs text-slate-500 font-mono mb-2">
                <span className="text-indigo-600 font-semibold">● Provenance</span>
                <span className="font-bold text-slate-900">78</span>
              </div>
              <h4 className="text-base font-bold text-slate-950 leading-snug mb-2">
                Your next fraudulent customer will be an agent — make it show ID
              </h4>
              <p className="text-xs text-slate-600 leading-relaxed">
                Cryptographic delegation credentials let a merchant verify an autonomous shopping agent acts for a real, accountable customer — spend caps and revocation included — in 40ms at checkout. The know-your-agent standard war starts now.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* THE PAPERS Section */}
      <section className="my-10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs font-bold font-mono tracking-wider uppercase text-slate-900 flex items-center gap-1.5">
            <span className="text-teal-600">■</span> The Papers
          </h2>
          <Link href="/papers" className="text-xs text-teal-600 hover:text-teal-700 font-semibold flex items-center gap-1">
            All papers <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* Tab Filters */}
        <div className="flex items-center justify-between border-b border-[#e5e7eb] mb-6">
          <div className="flex items-center gap-6">
            <button
              onClick={() => setActiveTab('score')}
              className={`pb-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-colors ${
                activeTab === 'score'
                  ? 'border-teal-600 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-900'
              }`}
            >
              <Radio className="w-3.5 h-3.5" />
              Overall score
            </button>

            <button
              onClick={() => setActiveTab('fit')}
              className={`pb-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-colors ${
                activeTab === 'fit'
                  ? 'border-teal-600 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-900'
              }`}
            >
              <Briefcase className="w-3.5 h-3.5" />
              Schwarz Fit
            </button>

            <button
              onClick={() => setActiveTab('novelty')}
              className={`pb-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-colors ${
                activeTab === 'novelty'
                  ? 'border-teal-600 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-900'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              Novelty
            </button>

            <button
              onClick={() => setActiveTab('significance')}
              className={`pb-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-colors ${
                activeTab === 'significance'
                  ? 'border-teal-600 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-900'
              }`}
            >
              <Zap className="w-3.5 h-3.5" />
              Significance
            </button>

            <button
              onClick={() => setActiveTab('rigour')}
              className={`pb-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-colors ${
                activeTab === 'rigour'
                  ? 'border-teal-600 text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-900'
              }`}
            >
              <Scale className="w-3.5 h-3.5" />
              Rigour
            </button>
          </div>

          <div className="text-xs text-slate-400 font-mono pb-3">
            {mockPapers.length} papers
          </div>
        </div>

        {/* Paper Items List */}
        <div className="space-y-4">
          {mockPapers.map((paper) => (
            <div
              key={paper.id}
              className="bg-white border border-[#e5e7eb] rounded-xl p-5 sm:p-6 hover:border-slate-300 transition-colors"
            >
              <div className="flex items-start gap-4">
                {/* Signal Badge */}
                <div className="w-12 h-12 rounded-full border-2 border-teal-500 flex items-center justify-center font-extrabold text-base text-slate-900 flex-shrink-0 mt-0.5">
                  {paper.score}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  {/* Meta Bar */}
                  <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-1.5 flex-wrap">
                    <span className="font-semibold text-slate-800">● {paper.sector}</span>
                    <span>·</span>
                    <span>{paper.source}</span>
                    <span>·</span>
                    <span>{paper.date}</span>
                    {paper.starred && <Star className="w-3 h-3 text-amber-500 fill-amber-500" />}
                  </div>

                  {/* Title */}
                  <Link href={`/papers/${paper.id}`} className="group">
                    <h3 className="text-base sm:text-lg font-bold text-slate-950 leading-snug mb-1.5 group-hover:text-teal-700 transition-colors">
                      {paper.title}
                    </h3>
                  </Link>

                  {/* Summary */}
                  <p className="text-xs sm:text-sm text-slate-600 leading-relaxed mb-3">
                    {paper.summary}
                  </p>

                  {/* Bottom Metrics Pill Bar */}
                  <div className="flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-semibold">
                        TRL {paper.trl} · {paper.stage}
                      </span>
                      <span className="text-slate-500">
                        Novelty <strong className="text-slate-800">{paper.novelty}</strong>
                      </span>
                      <span className="text-slate-500">
                        Significance <strong className="text-slate-800">{paper.significance}</strong>
                      </span>
                    </div>

                    <div className="text-slate-400 font-sans font-medium text-xs">
                      {paper.lab}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

    </div>
  );
}
