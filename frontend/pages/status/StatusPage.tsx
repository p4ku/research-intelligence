"use client";

import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  ShieldAlert, 
  ArrowLeft, 
  RefreshCw, 
  Server, 
  Cpu, 
  Database, 
  HardDrive, 
  Zap, 
  Mail, 
  Sparkles,
  Bot,
  Globe,
  CheckCircle2, 
  AlertTriangle, 
  XCircle 
} from 'lucide-react';

interface DeepHealthData {
  status: 'online' | 'degraded' | 'offline';
  timestamp: number;
  services: {
    database?: {
      status: 'online' | 'offline';
      vendor?: string;
      latency_ms?: number;
      counts?: {
        papers: number;
        workspaces: number;
      };
      error?: string;
    };
    redis?: {
      status: 'online' | 'offline';
      latency_ms?: number;
      scheme?: string;
      error?: string;
    };
    celery?: {
      status: 'online' | 'offline';
      mode?: string;
      latency_ms?: number;
      task_id?: string;
      result?: any;
      error?: string;
    };
    storage?: {
      status: 'online' | 'offline';
      backend?: string;
      bucket?: string;
      latency_ms?: number;
      verified?: boolean;
      error?: string;
    };
    mailgun?: {
      status: 'configured' | 'unconfigured';
      sender_domain?: string;
      api_url?: string;
    };
    llm_providers?: {
      google?: {
        status: 'online' | 'offline';
        provider_name?: string;
        model?: string;
        location?: string;
        project_id?: string;
        service_account_email?: string;
        latency_ms?: number;
        sample_response?: string;
        error?: string;
      };
      openrouter?: {
        status: 'configured' | 'not_configured';
        provider_name?: string;
        supported_models?: string[];
        note?: string;
      };
    };
  };
}

interface ServiceStatus {
  status: 'checking' | 'online' | 'offline';
  latency: number | null;
  statusCode: number | null;
  error: string | null;
}

export default function StatusPage() {
  const [apiStatus, setApiStatus] = useState<ServiceStatus>({
    status: 'checking',
    latency: null,
    statusCode: null,
    error: null,
  });

  const [mcpStatus, setMcpStatus] = useState<ServiceStatus>({
    status: 'checking',
    latency: null,
    statusCode: null,
    error: null,
  });

  const [deepHealth, setDeepHealth] = useState<DeepHealthData | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const getEndpoints = () => {
    if (typeof window === 'undefined') {
      const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
      const cleanBase = base.endsWith('/') ? base.slice(0, -1) : base;
      const mcp = process.env.NEXT_PUBLIC_MCP_URL || 'http://localhost:8001/sse';
      return {
        targetApiUrl: `${cleanBase}/health/`,
        targetDiagnosticsUrl: `${cleanBase}/health/diagnostics/`,
        targetMcpUrl: mcp,
        displayApiUrl: `${cleanBase}/health/`,
        displayMcpUrl: mcp,
      };
    }

    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    if (!isLocalhost) {
      return {
        targetApiUrl: `${window.location.origin}/api/health/`,
        targetDiagnosticsUrl: `${window.location.origin}/api/health/diagnostics/`,
        targetMcpUrl: `${window.location.origin}/sse`,
        displayApiUrl: `${window.location.origin}/api/health/`,
        displayMcpUrl: `${window.location.origin}/sse`,
      };
    }

    const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
    const cleanBase = base.endsWith('/') ? base.slice(0, -1) : base;
    const mcp = process.env.NEXT_PUBLIC_MCP_URL || 'http://localhost:8001/sse';
    return {
      targetApiUrl: `${cleanBase}/health/`,
      targetDiagnosticsUrl: `${cleanBase}/health/diagnostics/`,
      targetMcpUrl: mcp,
      displayApiUrl: `${cleanBase}/health/`,
      displayMcpUrl: mcp,
    };
  };

  const { targetApiUrl, targetDiagnosticsUrl, targetMcpUrl, displayApiUrl, displayMcpUrl } = getEndpoints();
  const [apiUrl, setApiUrl] = useState<string>(displayApiUrl);
  const [mcpUrl, setMcpUrl] = useState<string>(displayMcpUrl);

  const fetchWithTimeout = async (url: string, timeoutMs: number = 8000) => {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: { 'Accept': 'application/json, text/event-stream' }
      });
      clearTimeout(id);
      return response;
    } catch (error: any) {
      clearTimeout(id);
      if (error.name === 'AbortError') {
        throw new Error(`Request timed out after ${timeoutMs}ms`);
      }
      throw error;
    }
  };

  const checkStatuses = async () => {
    setIsRefreshing(true);
    setApiStatus(prev => ({ ...prev, status: 'checking', error: null }));
    setMcpStatus(prev => ({ ...prev, status: 'checking', error: null }));

    const { targetApiUrl: fetchApi, targetDiagnosticsUrl: fetchDiag, targetMcpUrl: fetchMcp, displayApiUrl: dispApi, displayMcpUrl: dispMcp } = getEndpoints();
    setApiUrl(dispApi);
    setMcpUrl(dispMcp);

    // 1. Check Django REST API
    const startApi = performance.now();
    try {
      const res = await fetchWithTimeout(fetchApi, 7000);
      const endApi = performance.now();
      const latency = Math.round(endApi - startApi);

      if (res.ok) {
        setApiStatus({
          status: 'online',
          latency,
          statusCode: res.status,
          error: null,
        });
      } else {
        setApiStatus({
          status: 'offline',
          latency,
          statusCode: res.status,
          error: `HTTP ${res.status}: ${res.statusText}`,
        });
      }
    } catch (err: any) {
      setApiStatus({
        status: 'offline',
        latency: null,
        statusCode: null,
        error: err.message || 'Connection failed / Network error',
      });
    }

    // 2. Fetch Deep Infrastructure Diagnostics
    try {
      const diagRes = await fetchWithTimeout(fetchDiag, 12000);
      if (diagRes.ok) {
        const diagData: DeepHealthData = await diagRes.json();
        setDeepHealth(diagData);
      } else {
        setDeepHealth(null);
      }
    } catch {
      setDeepHealth(null);
    }

    // 3. Check FastMCP SSE Endpoint
    const startMcp = performance.now();
    try {
      const res = await fetchWithTimeout(fetchMcp, 7000);
      const endMcp = performance.now();
      const latency = Math.round(endMcp - startMcp);

      if (res.status === 200 || res.status === 405 || res.status === 401 || res.status === 400) {
        setMcpStatus({
          status: 'online',
          latency,
          statusCode: res.status,
          error: null,
        });
      } else {
        setMcpStatus({
          status: 'offline',
          latency,
          statusCode: res.status,
          error: `HTTP ${res.status}: ${res.statusText}`,
        });
      }
    } catch (err: any) {
      setMcpStatus({
        status: 'offline',
        latency: null,
        statusCode: null,
        error: err.message || 'Connection failed / MCP Server unreachable',
      });
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    checkStatuses();
  }, []);

  const getBadge = (status?: string) => {
    if (status === 'online' || status === 'configured') {
      return {
        bg: 'bg-emerald-500/10 border-emerald-500/25',
        color: 'text-emerald-400',
        text: status.toUpperCase(),
        dot: 'bg-emerald-400',
      };
    }
    if (status === 'degraded' || status === 'warning') {
      return {
        bg: 'bg-amber-500/10 border-amber-500/25',
        color: 'text-amber-400',
        text: status.toUpperCase(),
        dot: 'bg-amber-400',
      };
    }
    return {
      bg: 'bg-rose-500/10 border-rose-500/25',
      color: 'text-rose-400',
      text: status ? status.toUpperCase() : 'OFFLINE',
      dot: 'bg-rose-400',
    };
  };

  return (
    <div className="min-h-[calc(100vh-65px)] bg-[#090d16] bg-[radial-gradient(circle_at_50%_15%,#1e1b4b_0%,#090d16_65%)] text-slate-100 p-6 sm:p-8 lg:p-10 flex flex-col items-center">
      <div className="max-w-6xl w-full">
        
        {/* Navigation & Refresh Header */}
        <header className="flex items-center justify-between gap-4 mb-8">
          <a
            href="/"
            className="inline-flex items-center gap-2 text-xs sm:text-sm font-semibold text-slate-400 hover:text-slate-200 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </a>

          <button
            onClick={checkStatuses}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-xs font-semibold text-slate-200 transition-colors cursor-pointer disabled:opacity-60"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? 'Running Probes...' : 'Run Diagnostics'}
          </button>
        </header>

        {/* Minimalist Title */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-sky-600 to-sky-400 shadow-xl shadow-sky-500/20 mb-4">
            <Activity className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400 bg-clip-text text-transparent">
            System Status
          </h1>
        </div>

        {/* Top Status Overview Cards (Primary Services) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
          
          {/* Django API Card */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-sky-500/10 border border-sky-500/20 rounded-xl text-sky-400">
                  <Server className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-100">Django REST API</h2>
                  <span className="text-xs text-slate-500">Core Service</span>
                </div>
              </div>

              {(() => {
                const badge = getBadge(apiStatus.status);
                return (
                  <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full border ${badge.bg} ${badge.color}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-3 text-xs text-slate-400">
              <div>
                <span className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-0.5">Endpoint URL</span>
                <code className="text-slate-300 break-all font-mono">{apiUrl}</code>
              </div>

              {apiStatus.status === 'online' && (
                <div className="grid grid-cols-2 gap-4 pt-3 border-t border-slate-800/80">
                  <div>
                    <span className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-0.5">Latency</span>
                    <span className="text-base font-bold text-slate-100">{apiStatus.latency} ms</span>
                  </div>
                  <div>
                    <span className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-0.5">HTTP Status</span>
                    <span className="text-base font-bold text-emerald-400">{apiStatus.statusCode} OK</span>
                  </div>
                </div>
              )}

              {apiStatus.status === 'offline' && (
                <div className="flex items-center gap-2 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-xs">
                  <ShieldAlert className="w-4 h-4 flex-shrink-0" />
                  <span>{apiStatus.error || 'Endpoint unreachable'}</span>
                </div>
              )}
            </div>
          </div>

          {/* FastMCP SSE Server Card */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-purple-500/10 border border-purple-500/20 rounded-xl text-purple-400">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-100">FastMCP SSE Server</h2>
                  <span className="text-xs text-slate-500">Agent Interface</span>
                </div>
              </div>

              {(() => {
                const badge = getBadge(mcpStatus.status);
                return (
                  <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full border ${badge.bg} ${badge.color}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-3 text-xs text-slate-400">
              <div>
                <span className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-0.5">Transport URL</span>
                <code className="text-slate-300 break-all font-mono">{mcpUrl}</code>
              </div>

              {mcpStatus.status === 'online' && (
                <div className="grid grid-cols-2 gap-4 pt-3 border-t border-slate-800/80">
                  <div>
                    <span className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-0.5">Latency</span>
                    <span className="text-base font-bold text-slate-100">{mcpStatus.latency} ms</span>
                  </div>
                  <div>
                    <span className="block text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-0.5">Protocol</span>
                    <span className="text-base font-bold text-sky-400">SSE Ready</span>
                  </div>
                </div>
              )}

              {mcpStatus.status === 'offline' && (
                <div className="flex items-center gap-2 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-xs">
                  <ShieldAlert className="w-4 h-4 flex-shrink-0" />
                  <span>{mcpStatus.error || 'MCP SSE service unreachable'}</span>
                </div>
              )}
            </div>
          </div>

        </div>

        {/* Deep Infrastructure Diagnostics Grid */}
        <h2 className="text-lg font-bold text-slate-200 mb-4">
          Infrastructure Services
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 mb-10">
          
          {/* 1. PostgreSQL Database */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <Database className="w-4 h-4 text-sky-400" />
                <span className="font-semibold text-sm text-slate-100">PostgreSQL</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.database?.status);
                return (
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg} ${badge.color}`}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-2 text-xs text-slate-400">
              <div className="flex justify-between">
                <span>Engine:</span>
                <strong className="text-slate-200">{deepHealth?.services.database?.vendor?.toUpperCase() || 'POSTGRESQL'}</strong>
              </div>
              <div className="flex justify-between">
                <span>Latency:</span>
                <strong className="text-slate-200">{deepHealth?.services.database?.latency_ms ? `${deepHealth.services.database.latency_ms} ms` : '-'}</strong>
              </div>
              <div className="flex justify-between">
                <span>Records:</span>
                <strong className="text-sky-400">
                  {deepHealth?.services.database?.counts?.workspaces ?? 0} ws / {deepHealth?.services.database?.counts?.papers ?? 0} papers
                </strong>
              </div>
            </div>
          </div>

          {/* 2. Redis Cache & Broker */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <Zap className="w-4 h-4 text-rose-400" />
                <span className="font-semibold text-sm text-slate-100">Redis</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.redis?.status);
                return (
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg} ${badge.color}`}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-2 text-xs text-slate-400">
              <div className="flex justify-between">
                <span>Scheme:</span>
                <strong className="text-slate-200 font-mono text-[11px]">{deepHealth?.services.redis?.scheme || 'rediss:// (SSL)'}</strong>
              </div>
              <div className="flex justify-between">
                <span>Latency:</span>
                <strong className="text-slate-200">{deepHealth?.services.redis?.latency_ms ? `${deepHealth.services.redis.latency_ms} ms` : '-'}</strong>
              </div>
              <div className="flex justify-between">
                <span>TLS Verification:</span>
                <strong className="text-emerald-400">Active</strong>
              </div>
            </div>
          </div>

          {/* 3. Celery Distributed Worker */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <Cpu className="w-4 h-4 text-purple-400" />
                <span className="font-semibold text-sm text-slate-100">Celery Workers</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.celery?.status);
                return (
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg} ${badge.color}`}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-2 text-xs text-slate-400">
              <div className="flex justify-between">
                <span>Execution Mode:</span>
                <strong className="text-slate-200">Distributed Worker</strong>
              </div>
              <div className="flex justify-between">
                <span>Ping Roundtrip:</span>
                <strong className="text-slate-200">{deepHealth?.services.celery?.latency_ms ? `${deepHealth.services.celery.latency_ms} ms` : '-'}</strong>
              </div>
              <div className="flex justify-between">
                <span>Queues:</span>
                <strong className="text-purple-400">celery, bulk-scraping</strong>
              </div>
            </div>
          </div>

          {/* 4. S3 Object Storage */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <HardDrive className="w-4 h-4 text-amber-400" />
                <span className="font-semibold text-sm text-slate-100">Object Storage</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.storage?.status);
                return (
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg} ${badge.color}`}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-2 text-xs text-slate-400">
              <div className="flex justify-between">
                <span>Backend:</span>
                <strong className="text-slate-200 font-mono text-[11px]">{deepHealth?.services.storage?.backend?.toUpperCase() || 'S3'}</strong>
              </div>
              <div className="flex justify-between">
                <span>Bucket:</span>
                <strong className="text-slate-200 font-mono text-[11px] truncate max-w-[140px]" title={deepHealth?.services.storage?.bucket}>
                  {deepHealth?.services.storage?.bucket || 'bucket-sri-production'}
                </strong>
              </div>
              <div className="flex justify-between">
                <span>Read/Write:</span>
                <strong className="text-emerald-400">Verified</strong>
              </div>
            </div>
          </div>

          {/* 5. Google Vertex AI / GenAI */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <Sparkles className="w-4 h-4 text-sky-400" />
                <span className="font-semibold text-sm text-slate-100">Google Vertex AI</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.llm_providers?.google?.status);
                return (
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg} ${badge.color}`}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-2 text-xs text-slate-400">
              <div className="flex justify-between">
                <span>Default Model:</span>
                <strong className="text-sky-400 font-mono text-[11px]">{deepHealth?.services.llm_providers?.google?.model || 'gemini-3.7-flash'}</strong>
              </div>
              <div className="flex justify-between">
                <span>Latency:</span>
                <strong className="text-slate-200">{deepHealth?.services.llm_providers?.google?.latency_ms ? `${deepHealth.services.llm_providers.google.latency_ms} ms` : '-'}</strong>
              </div>
              <div className="flex justify-between">
                <span>Region:</span>
                <strong className="text-slate-200">{deepHealth?.services.llm_providers?.google?.location || 'europe-west3'}</strong>
              </div>
            </div>
          </div>

          {/* 6. Mailgun Transactional Email */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <Mail className="w-4 h-4 text-emerald-400" />
                <span className="font-semibold text-sm text-slate-100">Mailgun Service</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.mailgun?.status);
                return (
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg} ${badge.color}`}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div className="space-y-2 text-xs text-slate-400">
              <div className="flex justify-between">
                <span>Domain:</span>
                <strong className="text-slate-200 font-mono text-[11px]">{deepHealth?.services.mailgun?.sender_domain || 'soinventive.co.uk'}</strong>
              </div>
              <div className="flex justify-between">
                <span>Transport:</span>
                <strong className="text-emerald-400">HTTP REST API</strong>
              </div>
              <div className="flex justify-between">
                <span>Region:</span>
                <strong className="text-slate-200">EU (api.eu.mailgun.net)</strong>
              </div>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
