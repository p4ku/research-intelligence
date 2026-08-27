"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { 
  Search, 
  Star, 
  ChevronDown 
} from 'lucide-react';

interface PaperItem {
  id: string;
  score: number;
  sector: string;
  source: string;
  date: string;
  starred: boolean;
  title: string;
  summary: string;
  trl: number;
  stage: string;
  novelty: number;
  significance: number;
  lab: string;
}

const mockPapersList: PaperItem[] = [
  {
    id: 'every-sku-one-policy',
    score: 85,
    sector: 'Physical AI',
    source: 'arXiv · cs.RO',
    date: 'Jun 29, 2026',
    starred: true,
    title: 'Every SKU, One Policy: A Generalist Vision-Language-Action Model from 10,000 Hours of Warehouse Teleoperation',
    summary: 'One policy, trained on real warehouse teleop, picks unseen SKUs at 91% first-attempt success — at production cycle times, in live facilities.',
    trl: 6,
    stage: 'Development',
    novelty: 84,
    significance: 90,
    lab: 'Vela Robotics',
  },
  {
    id: 'consolidated-memory',
    score: 84,
    sector: 'Agentic AI',
    source: 'arXiv · cs.MA',
    date: 'Jun 28, 2026',
    starred: false,
    title: 'Consolidated Memory: Learned Retrieval and Forgetting for Long-Horizon Agents',
    summary: 'Agents get a real memory: learned store-retrieve-forget beats stuffing transcripts into context, 31% better at 1/6 the tokens.',
    trl: 4,
    stage: 'Development',
    novelty: 86,
    significance: 88,
    lab: 'Meridian AI Lab',
  },
  {
    id: 'provenance-survives-internet',
    score: 82,
    sector: 'Provenance',
    source: 'arXiv · cs.CR',
    date: 'Jul 1, 2026',
    starred: true,
    title: 'Provenance That Survives the Internet: Durable Content Credentials Through Re-Encoding, Cropping, and Platform Pipelines',
    summary: 'Content credentials that survive being posted: manifest + soft-binding watermark recovers provenance for 94% of assets after real platform pipelines, vs 31% today.',
    trl: 6,
    stage: 'Development',
    novelty: 78,
    significance: 87,
    lab: 'TrustFabric',
  },
  {
    id: 'verifier-in-the-loop',
    score: 79,
    sector: 'Agentic AI',
    source: 'arXiv · cs.MA',
    date: 'Jun 24, 2026',
    starred: true,
    title: 'Verifier-in-the-Loop: Deterministic Control Flow for Multi-Agent Systems',
    summary: 'Treat agent fleets like workflow engines with a verifier gating every step — 44% fewer catastrophic failures than debate.',
    trl: 4,
    stage: 'Development',
    novelty: 72,
    significance: 84,
    lab: 'Northwind Research',
  },
  {
    id: 'provenance-first-pipelines',
    score: 78,
    sector: 'Provenance',
    source: 'arXiv · cs.CR',
    date: 'Jun 30, 2026',
    starred: false,
    title: 'Provenance-First Pipelines: End-to-End C2PA Signing for Generated Media',
    summary: 'Sign everything at generation time, verify at the gateway — C2PA provenance as pipeline infrastructure, deployed in a newsroom.',
    trl: 7,
    stage: 'Deployment',
    novelty: 63,
    significance: 85,
    lab: 'TrustFabric',
  },
  {
    id: 'know-your-agent',
    score: 78,
    sector: 'Provenance',
    source: 'arXiv · cs.CR',
    date: 'Jun 20, 2026',
    starred: false,
    title: 'Know Your Agent: Verifiable Delegation Credentials for Autonomous Shopping',
    summary: 'Cryptographic "know your agent" credentials — merchants verify an autonomous shopper acts for a real, accountable customer, with spend caps and revocation, in 40ms.',
    trl: 4,
    stage: 'Development',
    novelty: 82,
    significance: 84,
    lab: 'Basel Digital Trust Lab',
  },
  {
    id: 'imagined-rollouts',
    score: 77,
    sector: 'Physical AI',
    source: 'arXiv · cs.RO',
    date: 'Jun 11, 2026',
    starred: false,
    title: 'Imagined Rollouts: World Models as Planners for Language Agents',
    summary: 'Language agent plans by imagining rollouts in a learned world model; beats language-only and RL-only, transfers sim-to-real.',
    trl: 3,
    stage: 'Research',
    novelty: 90,
    significance: 89,
    lab: 'Helix Robotics',
  },
];

export default function PapersPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSector, setSelectedSector] = useState('Agentic AI / MAS');
  const [selectedTimeframe, setSelectedTimeframe] = useState('All time');
  const [starredOnly, setStarredOnly] = useState(false);
  const [codeOnly, setCodeOnly] = useState(false);

  const sectors = [
    'Agentic AI / MAS',
    'AI Native Development & Ephemeral Code',
    'AI Supercomputing',
    'Bio-Digital Synthesis & Deep Biotech',
    'Confidential Computing & Hybrid Infrastructure',
    'Digital Provenance & Trust',
    'Physical AI & Humanoids',
    'Preemptive Cybersecurity',
    'Quantum-Safe Crypto',
    'Sovereign AI / Geopatriation & Multi-Vendor Agility',
  ];

  return (
    <div className="p-8 sm:p-10 max-w-7xl mx-auto">
      
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-500 mb-1">
          <span className="text-teal-600 font-bold">■</span> CORPUS
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-950">
          Papers
        </h1>
      </div>

      {/* Search Bar */}
      <div className="relative mb-6">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search titles, abstracts, authors, labs..."
          className="w-full bg-white border border-[#e5e7eb] rounded-lg px-4 py-3 pl-10 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 transition-all"
        />
        <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
      </div>

      {/* Main Split Layout */}
      <div className="flex flex-col lg:flex-row gap-8">
        
        {/* Left Column: Papers List */}
        <div className="flex-1 min-w-0">
          <div className="text-xs font-mono text-slate-500 mb-4">
            <span className="font-bold text-slate-900">{mockPapersList.length} papers</span> · in focus · full corpus
          </div>

          <div className="space-y-4">
            {mockPapersList.map((paper) => (
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
                    <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-1.5 flex-wrap">
                      <span className="font-semibold text-slate-800">● {paper.sector}</span>
                      <span>·</span>
                      <span>{paper.source}</span>
                      <span>·</span>
                      <span>{paper.date}</span>
                      {paper.starred && <Star className="w-3 h-3 text-amber-500 fill-amber-500" />}
                    </div>

                    <Link href={`/papers/${paper.id}`} className="group">
                      <h3 className="text-base sm:text-lg font-bold text-slate-950 leading-snug mb-1.5 group-hover:text-teal-700 transition-colors">
                        {paper.title}
                      </h3>
                    </Link>

                    <p className="text-xs sm:text-sm text-slate-600 leading-relaxed mb-3">
                      {paper.summary}
                    </p>

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
        </div>

        {/* Right Column: Filter Panel */}
        <div className="w-full lg:w-80 flex-shrink-0 space-y-6">
          
          {/* SORT BY */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5">
            <div className="flex items-center justify-between text-xs font-mono uppercase font-bold text-slate-900 mb-3">
              <span className="flex items-center gap-1.5"><span className="text-teal-600">■</span> SORT BY</span>
              <span className="text-slate-400 text-[11px] flex items-center gap-1">Signal score <ChevronDown className="w-3 h-3" /></span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="px-2.5 py-1.5 rounded bg-slate-100 font-semibold text-slate-900">
                ● Signal score
              </div>
              <div className="px-2.5 py-1.5 text-slate-600 hover:text-slate-900 cursor-pointer">
                Most recent
              </div>
              <div className="px-2.5 py-1.5 text-slate-600 hover:text-slate-900 cursor-pointer">
                Novelty
              </div>
            </div>
          </div>

          {/* SECTORS */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5">
            <div className="flex items-center justify-between text-xs font-mono uppercase font-bold text-slate-900 mb-3">
              <span className="flex items-center gap-1.5"><span className="text-teal-600">■</span> SECTOR</span>
              <span className="text-slate-400 text-[11px] flex items-center gap-1">Focus sectors <ChevronDown className="w-3 h-3" /></span>
            </div>
            <div className="space-y-1 text-xs">
              {sectors.map((sec) => (
                <div
                  key={sec}
                  onClick={() => setSelectedSector(sec)}
                  className={`px-2.5 py-1.5 rounded cursor-pointer transition-colors ${
                    selectedSector === sec
                      ? 'bg-slate-100 font-semibold text-slate-900'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <span className="inline-block w-2 text-slate-400 mr-1.5">●</span>
                  {sec}
                </div>
              ))}
            </div>
          </div>

          {/* PUBLISHED */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5">
            <div className="flex items-center justify-between text-xs font-mono uppercase font-bold text-slate-900 mb-3">
              <span className="flex items-center gap-1.5"><span className="text-teal-600">■</span> PUBLISHED</span>
              <span className="text-slate-400 text-[11px] flex items-center gap-1">All time <ChevronDown className="w-3 h-3" /></span>
            </div>
            <div className="space-y-1 text-xs">
              {['Last 24 hours', 'Last 7 days', 'Last 30 days', 'This quarter', 'All time'].map((t) => (
                <div
                  key={t}
                  onClick={() => setSelectedTimeframe(t)}
                  className={`px-2.5 py-1.5 rounded cursor-pointer transition-colors ${
                    selectedTimeframe === t
                      ? 'bg-slate-100 font-semibold text-slate-900'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  {selectedTimeframe === t && <span className="inline-block w-2 text-slate-400 mr-1.5">●</span>}
                  {t}
                </div>
              ))}
            </div>
          </div>

          {/* SIGNAL STRENGTH */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5">
            <div className="flex items-center justify-between text-xs font-mono uppercase font-bold text-slate-900 mb-3">
              <span className="flex items-center gap-1.5"><span className="text-teal-600">■</span> SIGNAL STRENGTH</span>
              <span className="text-slate-400 text-[11px] flex items-center gap-1">Any signal <ChevronDown className="w-3 h-3" /></span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="px-2.5 py-1.5 rounded bg-slate-100 font-semibold text-slate-900">
                ● Any signal
              </div>
              <div className="px-2.5 py-1.5 text-slate-600 hover:text-slate-900 cursor-pointer">
                Worth a look
              </div>
              <div className="px-2.5 py-1.5 text-slate-600 hover:text-slate-900 cursor-pointer">
                Strong signal
              </div>
            </div>
          </div>

          {/* REFINE */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5">
            <div className="flex items-center justify-between text-xs font-mono uppercase font-bold text-slate-900 mb-3">
              <span className="flex items-center gap-1.5"><span className="text-teal-600">■</span> REFINE</span>
              <span className="text-slate-400 text-[11px] flex items-center gap-1">Any <ChevronDown className="w-3 h-3" /></span>
            </div>
            <div className="space-y-3 text-xs">
              <label className="flex items-center justify-between cursor-pointer">
                <span className="flex items-center gap-1.5 text-slate-700">
                  <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" /> Starred only
                </span>
                <input
                  type="checkbox"
                  checked={starredOnly}
                  onChange={(e) => setStarredOnly(e.target.checked)}
                  className="rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <span className="text-slate-700">Code released only</span>
                <input
                  type="checkbox"
                  checked={codeOnly}
                  onChange={(e) => setCodeOnly(e.target.checked)}
                  className="rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                />
              </label>
            </div>
          </div>

          {/* TRL WINDOW */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5">
            <div className="flex items-center justify-between text-xs font-mono uppercase font-bold text-slate-900 mb-3">
              <span className="flex items-center gap-1.5"><span className="text-teal-600">■</span> TRL WINDOW</span>
              <span className="text-slate-400 text-[11px]">1-9</span>
            </div>
            <div className="flex items-center gap-2 mb-2 text-xs">
              <select className="border border-[#e5e7eb] rounded px-2 py-1 bg-white text-slate-800">
                <option>1</option>
                <option>2</option>
                <option>3</option>
              </select>
              <span className="text-slate-400">to</span>
              <select className="border border-[#e5e7eb] rounded px-2 py-1 bg-white text-slate-800" defaultValue="9">
                <option>7</option>
                <option>8</option>
                <option>9</option>
              </select>
            </div>
            <div className="text-[10px] text-slate-400 font-mono">
              1-3 research · 4-6 development · 7-9 deployment
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
