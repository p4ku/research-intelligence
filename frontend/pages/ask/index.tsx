"use client";

import React, { useState } from 'react';
import { 
  Search, 
  Send, 
  Plus, 
  Sparkles, 
  ArrowRight,
  BookOpen
} from 'lucide-react';

interface HistoryItem {
  id: string;
  query: string;
  time: string;
  scope: string;
  color: string;
}

interface HistoryGroup {
  date: string;
  count: number;
  items: HistoryItem[];
}

const mockHistory: HistoryGroup[] = [
  {
    date: 'TODAY',
    count: 2,
    items: [
      {
        id: '1',
        query: "What's new in agent memory?",
        time: '09:18',
        scope: 'All papers · 3 cites',
        color: 'border-teal-500',
      },
      {
        id: '2',
        query: 'Are humanoids actually ready for our warehouses?',
        time: '09:12',
        scope: 'All papers · 4 cites',
        color: 'border-orange-500',
      },
    ],
  },
  {
    date: 'YESTERDAY',
    count: 3,
    items: [
      {
        id: '3',
        query: 'What would a Schwarz use case look like?',
        time: '16:32',
        scope: 'Consolidated Memory · full text',
        color: 'border-teal-500',
      },
      {
        id: '4',
        query: 'How exposed are we to deepfake and synthetic-media fraud?',
        time: '11:47',
        scope: 'All papers · 4 cites',
        color: 'border-indigo-500',
      },
      {
        id: '5',
        query: 'What does this actually enable?',
        time: '10:05',
        scope: 'Every SKU, One Policy · full text',
        color: 'border-orange-500',
      },
    ],
  },
  {
    date: 'TUE JUN 30',
    count: 3,
    items: [
      {
        id: '6',
        query: 'What would a Schwarz use case look like?',
        time: '15:21',
        scope: 'Provenance That Survives... · full text',
        color: 'border-indigo-500',
      },
      {
        id: '7',
        query: 'What does this actually enable?',
        time: '14:02',
        scope: 'Verifier-in-the-loop · full text',
        color: 'border-teal-500',
      },
      {
        id: '8',
        query: 'What is the strongest counter-argument?',
        time: '09:40',
        scope: 'LiveBench-Agent · full text',
        color: 'border-slate-500',
      },
    ],
  },
  {
    date: 'MON JUN 29',
    count: 2,
    items: [
      {
        id: '9',
        query: 'What is the strongest counter-argument?',
        time: '17:15',
        scope: 'Consolidated Memory · full text',
        color: 'border-teal-500',
      },
      {
        id: '10',
        query: 'What would a Schwarz use case look like?',
        time: '11:20',
        scope: 'Verifier-in-the-loop · full text',
        color: 'border-teal-500',
      },
    ],
  },
];

export default function AskPage() {
  const [scope, setScope] = useState<'all' | 'one'>('all');
  const [prompt, setPrompt] = useState('');
  const [activeQuery, setActiveQuery] = useState<string | null>(null);
  const [response, setResponse] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setActiveQuery(prompt);
    setResponse(null);
    const q = prompt;
    setPrompt('');

    setTimeout(() => {
      setResponse(`Across the ingested corpus, 3 recent papers (Vela Robotics, Meridian AI, and TrustFabric) indicate an accelerating trend toward real-world teleoperated learning and cryptographic credential binding. For Schwarz DC environments, the primary opportunity is in zero-shot SKU teleoperation (TRL 6).`);
    }, 500);
  };

  const handleSelectHistory = (item: HistoryItem) => {
    setActiveQuery(item.query);
    setResponse(`Synthesis for "${item.query}": Research findings confirm long-horizon memory architectures (Consolidated Memory) reduce context token overhead by 83% while improving long-sequence recall.`);
  };

  return (
    <div className="p-8 sm:p-10 max-w-7xl mx-auto">
      
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-500 mb-1">
          <span className="text-teal-600 font-bold">■</span> ASSISTANT
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-950">
          Ask Research Scanner
        </h1>
      </div>

      {/* Main Split Content */}
      <div className="flex flex-col lg:flex-row gap-8 items-start">
        
        {/* Left Column: Ask Input & Active Conversation */}
        <div className="flex-1 w-full space-y-6">
          
          {/* Ask Box Card */}
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-6 shadow-sm">
            <div className="flex items-center justify-between text-xs font-mono uppercase font-bold text-slate-400 mb-3">
              <span>ASK</span>
              <div className="flex items-center gap-1 p-0.5 rounded bg-slate-100 font-sans text-xs">
                <button
                  type="button"
                  onClick={() => setScope('all')}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    scope === 'all' ? 'bg-slate-900 text-white font-semibold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  All papers
                </button>
                <button
                  type="button"
                  onClick={() => setScope('one')}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    scope === 'one' ? 'bg-slate-900 text-white font-semibold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  One paper
                </button>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="relative">
              <input
                type="text"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Ask across all 32 papers..."
                className="w-full bg-[#f8f9fa] border border-[#e5e7eb] rounded-lg px-4 py-3 pl-10 pr-12 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:bg-white focus:border-slate-400 transition-all"
              />
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <button
                type="submit"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-teal-600 transition-colors p-1"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>

          {/* Response / Active Synthesis View */}
          {activeQuery && (
            <div className="bg-white border border-[#e5e7eb] rounded-xl p-6 sm:p-8 space-y-4">
              <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
                <Sparkles className="w-3.5 h-3.5 text-teal-600" />
                <span>QUERY:</span>
                <strong className="text-slate-900 font-semibold">{activeQuery}</strong>
              </div>

              {response ? (
                <div className="pt-3 border-t border-[#f1f5f9] text-sm text-slate-700 leading-relaxed space-y-3">
                  <p>{response}</p>
                  <div className="p-3 bg-slate-50 border border-slate-100 rounded-lg text-xs text-slate-500 font-mono flex items-center gap-2">
                    <BookOpen className="w-3.5 h-3.5 text-teal-600" />
                    <span>Evidence grounded in 4 peer-reviewed manuscripts with full citation trace.</span>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-slate-400 font-mono animate-pulse">
                  Synthesizing multi-document insights...
                </div>
              )}
            </div>
          )}

        </div>

        {/* Right Column: History Timeline */}
        <div className="w-full lg:w-96 flex-shrink-0">
          <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 shadow-sm">
            
            {/* History Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="text-xs font-mono uppercase font-bold text-slate-900 flex items-center gap-1.5">
                <span className="text-teal-600">■</span> History
                <span className="text-slate-400 text-[11px] font-normal ml-1">10 asked</span>
              </div>
              <button
                onClick={() => { setActiveQuery(null); setResponse(null); }}
                className="flex items-center gap-1 text-[11px] font-semibold bg-slate-900 text-white px-2.5 py-1 rounded hover:bg-slate-800 transition-colors"
              >
                <Plus className="w-3 h-3" /> New conversation
              </button>
            </div>

            {/* History Timeline List */}
            <div className="space-y-5">
              {mockHistory.map((group) => (
                <div key={group.date}>
                  <div className="flex justify-between items-center text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider mb-2 border-b border-[#f1f5f9] pb-1">
                    <span>{group.date}</span>
                    <span>{group.count}</span>
                  </div>

                  <div className="space-y-2">
                    {group.items.map((item) => (
                      <div
                        key={item.id}
                        onClick={() => handleSelectHistory(item)}
                        className={`p-2 rounded-lg hover:bg-slate-50 border-l-2 ${item.color} cursor-pointer transition-colors pl-2.5`}
                      >
                        <div className="text-xs font-medium text-slate-900 leading-snug hover:text-teal-700">
                          {item.query}
                        </div>
                        <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                          {item.time} · {item.scope}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

          </div>
        </div>

      </div>

    </div>
  );
}
