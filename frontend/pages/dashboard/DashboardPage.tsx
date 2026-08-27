"use client";

import React, { useState, useEffect } from 'react';
import { useAuth } from '../../lib/auth/auth-context';
import { workspaceService, WorkspaceItem } from '../../lib/services/workspace-service';
import { 
  Layers, 
  Sparkles, 
  Cpu, 
  Search, 
  Activity, 
  RefreshCw, 
  CheckCircle, 
  AlertCircle, 
  ShieldCheck, 
  Globe, 
  Database 
} from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const fetchWorkspaces = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await workspaceService.getWorkspaces();
      setWorkspaces(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch accessible workspaces');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkspaces();
  }, []);

  const filteredWorkspaces = workspaces.filter(ws => 
    ws.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ws.abstract_acceptance_criteria?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (ws.user_role && ws.user_role.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const getRoleBadge = (role?: string | null) => {
    const r = (role || (user?.is_superuser ? 'admin' : 'researcher')).toLowerCase();
    if (r === 'admin') {
      return { label: 'Admin', icon: '👑', color: 'bg-amber-500/15 text-amber-300 border-amber-500/30' };
    }
    if (r === 'manager') {
      return { label: 'Manager', icon: '🛡️', color: 'bg-purple-500/15 text-purple-300 border-purple-500/30' };
    }
    return { label: 'Researcher', icon: '🔬', color: 'bg-sky-500/15 text-sky-300 border-sky-500/30' };
  };

  return (
    <div className="min-h-[calc(100vh-65px)] bg-[#090d16] bg-[radial-gradient(circle_at_50%_10%,#1e1b4b_0%,#090d16_60%)] text-slate-100 flex flex-col items-center p-6 sm:p-8 lg:p-10">
      <div className="max-w-6xl w-full">
        
        {/* Welcome Header */}
        <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
          <div>
            <div className="inline-flex items-center gap-2 bg-sky-500/10 border border-sky-500/20 rounded-full px-3 py-1 text-xs font-semibold text-sky-400 mb-3">
              <ShieldCheck className="w-3.5 h-3.5" />
              Logged in as {user?.is_superuser ? 'Superuser' : (user?.email || user?.username)}
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-slate-100 to-slate-400 bg-clip-text text-transparent mb-1">
              Welcome back, {user?.first_name || user?.username}!
            </h1>
            <p className="text-sm sm:text-base text-slate-400">
              Your assigned systematic literature review projects and intelligence workspaces.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={fetchWorkspaces}
              disabled={isLoading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-xs font-semibold text-slate-200 transition-colors cursor-pointer disabled:opacity-60"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>

            <a
              href="/status"
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-sky-500/10 border border-sky-500/30 hover:bg-sky-500/20 text-xs font-semibold text-sky-400 transition-colors"
            >
              <Activity className="w-3.5 h-3.5" />
              System Diagnostics
            </a>
          </div>
        </div>

        {/* Quick KPI Overview Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-10">
          {/* Card 1: Accessible Workspaces */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-medium uppercase tracking-wider">Accessible Workspaces</span>
              <Layers className="w-5 h-5 text-sky-400" />
            </div>
            <div className="text-3xl font-extrabold text-white">
              {workspaces.length}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Role-based tenant memberships
            </div>
          </div>

          {/* Card 2: AI Reasoning Engine */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-medium uppercase tracking-wider">Screening Engine</span>
              <Cpu className="w-5 h-5 text-purple-400" />
            </div>
            <div className="text-2xl font-extrabold text-purple-300">
              Gemini 3.7 Flash
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Google Vertex AI (EU Sovereign)
            </div>
          </div>

          {/* Card 3: Ingestion Sources */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between text-slate-400 mb-3">
              <span className="text-xs font-medium uppercase tracking-wider">Scrapers & Ingestion</span>
              <Globe className="w-5 h-5 text-emerald-400" />
            </div>
            <div className="text-2xl font-extrabold text-emerald-300">
              ArXiv, OpenAlex, Lens
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Multi-source deduplication active
            </div>
          </div>
        </div>

        {/* Search & Filter Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <h2 className="text-xl font-bold text-slate-100">
            Your SLR Workspaces ({filteredWorkspaces.length})
          </h2>

          <div className="relative min-w-[280px]">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, role, or criteria..."
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 pl-9 text-xs sm:text-sm text-slate-100 placeholder:text-slate-500 outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-400 transition-all"
            />
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          </div>
        </div>

        {/* Error banner if any */}
        {error && (
          <div className="flex items-center gap-3 bg-rose-500/10 border border-rose-500/25 rounded-xl p-4 text-rose-400 text-sm mb-6">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Workspaces Grid */}
        {isLoading && workspaces.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-16 text-center text-slate-400">
            <RefreshCw className="w-7 h-7 text-sky-400 animate-spin mx-auto mb-4" />
            <div className="text-sm font-medium">Loading your workspace registry...</div>
          </div>
        ) : filteredWorkspaces.length === 0 ? (
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-16 text-center text-slate-400">
            <Layers className="w-10 h-10 text-slate-600 mx-auto mb-4" />
            <h3 className="text-lg font-bold text-slate-200 mb-2">No workspaces found</h3>
            <p className="text-xs sm:text-sm text-slate-500 max-w-md mx-auto leading-relaxed">
              {searchQuery 
                ? `No workspaces match "${searchQuery}". Try a different search term.` 
                : "You don't have any workspaces assigned yet. Create one via the REST API or FastMCP agent interface."}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredWorkspaces.map((ws) => {
              const roleBadge = getRoleBadge(ws.user_role);
              return (
                <div
                  key={ws.id}
                  className="bg-slate-900/80 border border-slate-800 hover:border-sky-500/50 rounded-2xl p-6 flex flex-col justify-between shadow-xl hover:-translate-y-1 transition-all"
                >
                  <div>
                    {/* Role & Model Header */}
                    <div className="flex items-center justify-between mb-3">
                      <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md border uppercase tracking-wider ${roleBadge.color}`}>
                        {roleBadge.icon} {roleBadge.label}
                      </span>

                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 uppercase tracking-wider">
                        {ws.screening_llm_model || 'gemini-3.7-flash'}
                      </span>
                    </div>

                    {/* Workspace Title */}
                    <h3 className="text-lg font-bold text-white mb-2 leading-snug">
                      {ws.name}
                    </h3>

                    {/* Criteria Snippet */}
                    {ws.abstract_acceptance_criteria && (
                      <div className="mb-4">
                        <span className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1">
                          Inclusion Criteria
                        </span>
                        <p className="text-xs text-slate-300 line-clamp-2 leading-relaxed">
                          {ws.abstract_acceptance_criteria}
                        </p>
                      </div>
                    )}

                    {/* Metadata Chips */}
                    <div className="flex flex-wrap gap-2 mb-6">
                      <span className="text-[11px] bg-slate-950 border border-slate-800 text-slate-400 px-2 py-1 rounded-lg">
                        📡 {ws.scrapers?.length || 0} Scrapers
                      </span>
                      <span className="text-[11px] bg-slate-950 border border-slate-800 text-slate-400 px-2 py-1 rounded-lg">
                        🎯 {ws.extraction_definitions?.length || 0} Targets
                      </span>
                      <span className="text-[11px] bg-slate-950 border border-slate-800 text-slate-400 px-2 py-1 rounded-lg">
                        📄 {ws.ocr_provider ? ws.ocr_provider.toUpperCase() : 'Multimodal'}
                      </span>
                    </div>
                  </div>

                  {/* Card Footer */}
                  <div className="border-t border-slate-800/80 pt-4 flex items-center justify-between text-xs">
                    <span className="text-slate-500 text-[11px]">
                      Created {new Date(ws.created_at).toLocaleDateString()}
                    </span>

                    <div className="flex items-center gap-1.5 text-sky-400 font-semibold">
                      <span>SLR Active</span>
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
