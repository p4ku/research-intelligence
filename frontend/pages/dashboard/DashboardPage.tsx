"use client";

import React, { useEffect, useState } from 'react';
import { useAuth } from '../../lib/auth/auth-context';
import { workspaceService, WorkspaceItem } from '../../lib/services/workspace-service';
import { 
  Layers, 
  Bot, 
  Search, 
  Sliders,
  AlertCircle,
  Clock
} from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchWorkspaces() {
      try {
        setIsLoading(true);
        const data = await workspaceService.getWorkspaces();
        setWorkspaces(data || []);
      } catch (err: any) {
        setError(err.message || 'Failed to load workspaces.');
      } finally {
        setIsLoading(false);
      }
    }
    fetchWorkspaces();
  }, []);

  const getRoleBadge = (role?: string | null) => {
    if (!role) {
      if (user?.is_superuser) {
        return <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-amber-50 text-amber-800 border border-amber-200">👑 Admin</span>;
      }
      return <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-teal-50 text-teal-800 border border-teal-200">🔬 Researcher</span>;
    }
    const r = role.toLowerCase();
    if (r === 'admin') {
      return <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-amber-50 text-amber-800 border border-amber-200">👑 Admin</span>;
    }
    if (r === 'manager') {
      return <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-indigo-50 text-indigo-800 border border-indigo-200">🛡️ Manager</span>;
    }
    return <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-teal-50 text-teal-800 border border-teal-200">🔬 Researcher</span>;
  };

  return (
    <div className="p-8 sm:p-10 max-w-6xl mx-auto">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[#f0f0f0] mb-8">
        <div>
          <div className="flex items-center gap-1.5 text-xs font-mono font-bold uppercase tracking-wider text-teal-700 mb-1">
            <span>■</span> WORKSPACES
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950">
            Research Workspaces
          </h1>
        </div>

        <div className="text-xs font-mono text-slate-500">
          <span className="font-bold text-slate-900">{workspaces.length}</span> active workspaces enrolled
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-xl mb-6">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Workspaces List */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-pulse">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-48 bg-slate-100 rounded-2xl border border-slate-200" />
          ))}
        </div>
      ) : workspaces.length === 0 ? (
        <div className="bg-white border border-[#e5e7eb] rounded-2xl p-12 text-center max-w-lg mx-auto shadow-sm">
          <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 mx-auto mb-4">
            <Layers className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-slate-900 mb-1">No Active Workspaces Found</h3>
          <p className="text-xs text-slate-500 mb-2">
            You are not currently enrolled in any research workspaces.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {workspaces.map((ws) => (
            <div
              key={ws.id}
              className="bg-white border border-[#e5e7eb] rounded-2xl p-6 hover:border-slate-300 hover:shadow-sm transition-all flex flex-col justify-between"
            >
              <div>
                {/* Top Role & Name */}
                <div className="flex items-start justify-between gap-3 mb-3">
                  <h3 className="text-lg font-bold text-slate-950 tracking-tight leading-snug">
                    {ws.name}
                  </h3>
                  {getRoleBadge(ws.user_role)}
                </div>

                {/* Criteria Snippets */}
                <div className="space-y-2 mb-4 text-xs text-slate-600">
                  <div className="p-3 bg-[#f8f9fa] rounded-xl border border-[#f1f5f9]">
                    <span className="text-[10px] font-mono font-bold uppercase text-slate-400 block mb-0.5">
                      Abstract Acceptance Criteria
                    </span>
                    <p className="line-clamp-2 text-slate-700 leading-relaxed">
                      {ws.abstract_acceptance_criteria || 'No criteria configured.'}
                    </p>
                  </div>

                  <div className="flex items-center gap-4 text-xs font-mono text-slate-500 pt-1">
                    <span className="flex items-center gap-1">
                      <Bot className="w-3.5 h-3.5 text-teal-600" />
                      {ws.screening_llm_model}
                    </span>
                    <span className="flex items-center gap-1">
                      <Search className="w-3.5 h-3.5 text-slate-400" />
                      {ws.scrapers?.length || 0} scrapers
                    </span>
                    <span className="flex items-center gap-1">
                      <Sliders className="w-3.5 h-3.5 text-slate-400" />
                      {ws.extraction_definitions?.length || 0} extractors
                    </span>
                  </div>
                </div>
              </div>

              {/* Bottom Metadata */}
              <div className="flex items-center justify-between pt-4 border-t border-[#f1f5f9] text-xs">
                <span className="text-slate-400 font-mono text-[11px] flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Created {new Date(ws.created_at).toLocaleDateString()}
                </span>
                <span className="text-teal-700 font-mono font-semibold text-[11px]">
                  Active Workspace
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

    </div>
  );
}
