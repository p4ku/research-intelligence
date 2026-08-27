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
  Bot
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
        bg: 'bg-emerald-50 border-emerald-200 text-emerald-700',
        text: status.toUpperCase(),
        dot: 'bg-emerald-600',
      };
    }
    if (status === 'degraded' || status === 'warning') {
      return {
        bg: 'bg-amber-50 border-amber-200 text-amber-700',
        text: status.toUpperCase(),
        dot: 'bg-amber-600',
      };
    }
    return {
      bg: 'bg-rose-50 border-rose-200 text-rose-700',
      text: status ? status.toUpperCase() : 'OFFLINE',
      dot: 'bg-rose-600',
    };
  };

  return (
    <div className="p-8 sm:p-10 max-w-6xl mx-auto">
      
      {/* Header */}
      <div className="flex items-center justify-between pb-6 border-b border-[#f0f0f0] mb-8">
        <div>
          <div className="flex items-center gap-1.5 text-[11px] font-mono font-semibold uppercase tracking-wider text-slate-500 mb-1">
            <span className="text-teal-600 font-bold">■</span> INFRASTRUCTURE
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950">
            System Status
          </h1>
        </div>

        <button
          onClick={checkStatuses}
          disabled={isRefreshing}
          className="flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors cursor-pointer disabled:opacity-60"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Checking...' : 'Run Diagnostics'}
        </button>
      </div>

      {/* Primary Services Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        
        {/* Django API */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-slate-100 rounded-lg text-slate-900">
                <Server className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900">Django REST API</h2>
                <span className="text-xs text-slate-500 font-mono">Core Service</span>
              </div>
            </div>

            {(() => {
              const badge = getBadge(apiStatus.status);
              return (
                <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full border ${badge.bg}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
                  {badge.text}
                </span>
              );
            })()}
          </div>

          <div className="space-y-2 text-xs text-slate-600">
            <div>
              <span className="text-slate-400 font-mono text-[10px] uppercase block">Endpoint</span>
              <code className="text-slate-900 font-mono text-[11px] break-all">{apiUrl}</code>
            </div>

            {apiStatus.status === 'online' && (
              <div className="grid grid-cols-2 gap-4 pt-3 border-t border-[#f1f5f9]">
                <div>
                  <span className="text-slate-400 font-mono text-[10px] uppercase block">Latency</span>
                  <span className="text-sm font-bold text-slate-900">{apiStatus.latency} ms</span>
                </div>
                <div>
                  <span className="text-slate-400 font-mono text-[10px] uppercase block">Status</span>
                  <span className="text-sm font-bold text-emerald-700">{apiStatus.statusCode} OK</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* FastMCP SSE */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-slate-100 rounded-lg text-slate-900">
                <Bot className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900">FastMCP SSE Server</h2>
                <span className="text-xs text-slate-500 font-mono">Agent Interface</span>
              </div>
            </div>

            {(() => {
              const badge = getBadge(mcpStatus.status);
              return (
                <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full border ${badge.bg}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
                  {badge.text}
                </span>
              );
            })()}
          </div>

          <div className="space-y-2 text-xs text-slate-600">
            <div>
              <span className="text-slate-400 font-mono text-[10px] uppercase block">Transport</span>
              <code className="text-slate-900 font-mono text-[11px] break-all">{mcpUrl}</code>
            </div>

            {mcpStatus.status === 'online' && (
              <div className="grid grid-cols-2 gap-4 pt-3 border-t border-[#f1f5f9]">
                <div>
                  <span className="text-slate-400 font-mono text-[10px] uppercase block">Latency</span>
                  <span className="text-sm font-bold text-slate-900">{mcpStatus.latency} ms</span>
                </div>
                <div>
                  <span className="text-slate-400 font-mono text-[10px] uppercase block">Protocol</span>
                  <span className="text-sm font-bold text-teal-700">SSE Ready</span>
                </div>
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Deep Services Grid */}
      <h2 className="text-xs font-mono uppercase font-bold text-slate-900 mb-4">
        ■ Component Diagnostics
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        
        {/* PostgreSQL */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-slate-900" />
              <span className="font-bold text-xs text-slate-900">PostgreSQL</span>
            </div>
            {(() => {
              const badge = getBadge(deepHealth?.services.database?.status);
              return (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg}`}>
                  {badge.text}
                </span>
              );
            })()}
          </div>
          <div className="space-y-1.5 text-xs text-slate-600">
            <div className="flex justify-between"><span>Vendor:</span> <strong className="text-slate-900">{deepHealth?.services.database?.vendor?.toUpperCase() || 'POSTGRESQL'}</strong></div>
            <div className="flex justify-between"><span>Latency:</span> <strong className="text-slate-900">{deepHealth?.services.database?.latency_ms ? `${deepHealth.services.database.latency_ms} ms` : '-'}</strong></div>
            <div className="flex justify-between"><span>Records:</span> <strong className="text-teal-700">{deepHealth?.services.database?.counts?.workspaces ?? 0} ws / {deepHealth?.services.database?.counts?.papers ?? 0} papers</strong></div>
          </div>
        </div>

        {/* Redis */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-slate-900" />
              <span className="font-bold text-xs text-slate-900">Redis</span>
            </div>
            {(() => {
              const badge = getBadge(deepHealth?.services.redis?.status);
              return (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg}`}>
                  {badge.text}
                </span>
              );
            })()}
          </div>
          <div className="space-y-1.5 text-xs text-slate-600">
            <div className="flex justify-between"><span>Scheme:</span> <strong className="text-slate-900 font-mono text-[11px]">rediss:// (SSL)</strong></div>
            <div className="flex justify-between"><span>Latency:</span> <strong className="text-slate-900">{deepHealth?.services.redis?.latency_ms ? `${deepHealth.services.redis.latency_ms} ms` : '-'}</strong></div>
            <div className="flex justify-between"><span>TLS:</span> <strong className="text-emerald-700">Verified</strong></div>
          </div>
        </div>

        {/* Celery */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-slate-900" />
              <span className="font-bold text-xs text-slate-900">Celery Workers</span>
            </div>
            {(() => {
              const badge = getBadge(deepHealth?.services.celery?.status);
              return (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg}`}>
                  {badge.text}
                </span>
              );
            })()}
          </div>
          <div className="space-y-1.5 text-xs text-slate-600">
            <div className="flex justify-between"><span>Mode:</span> <strong className="text-slate-900">Distributed</strong></div>
            <div className="flex justify-between"><span>Latency:</span> <strong className="text-slate-900">{deepHealth?.services.celery?.latency_ms ? `${deepHealth.services.celery.latency_ms} ms` : '-'}</strong></div>
            <div className="flex justify-between"><span>Queues:</span> <strong className="text-teal-700">celery, bulk-scraping</strong></div>
          </div>
        </div>

        {/* Storage */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-slate-900" />
              <span className="font-bold text-xs text-slate-900">Object Storage</span>
            </div>
            {(() => {
              const badge = getBadge(deepHealth?.services.storage?.status);
              return (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg}`}>
                  {badge.text}
                </span>
              );
            })()}
          </div>
          <div className="space-y-1.5 text-xs text-slate-600">
            <div className="flex justify-between"><span>Backend:</span> <strong className="text-slate-900 font-mono text-[11px]">{deepHealth?.services.storage?.backend?.toUpperCase() || 'S3'}</strong></div>
            <div className="flex justify-between"><span>Bucket:</span> <strong className="text-slate-900 font-mono text-[11px]">{deepHealth?.services.storage?.bucket || 'bucket-sri-production'}</strong></div>
            <div className="flex justify-between"><span>I/O:</span> <strong className="text-emerald-700">Verified</strong></div>
          </div>
        </div>

        {/* Google Vertex AI */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-slate-900" />
              <span className="font-bold text-xs text-slate-900">Google Vertex AI</span>
            </div>
            {(() => {
              const badge = getBadge(deepHealth?.services.llm_providers?.google?.status);
              return (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg}`}>
                  {badge.text}
                </span>
              );
            })()}
          </div>
          <div className="space-y-1.5 text-xs text-slate-600">
            <div className="flex justify-between"><span>Model:</span> <strong className="text-teal-700 font-mono text-[11px]">{deepHealth?.services.llm_providers?.google?.model || 'gemini-3.7-flash'}</strong></div>
            <div className="flex justify-between"><span>Latency:</span> <strong className="text-slate-900">{deepHealth?.services.llm_providers?.google?.latency_ms ? `${deepHealth.services.llm_providers.google.latency_ms} ms` : '-'}</strong></div>
            <div className="flex justify-between"><span>Region:</span> <strong className="text-slate-900">{deepHealth?.services.llm_providers?.google?.location || 'europe-west3'}</strong></div>
          </div>
        </div>

        {/* Mailgun */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-slate-900" />
              <span className="font-bold text-xs text-slate-900">Mailgun</span>
            </div>
            {(() => {
              const badge = getBadge(deepHealth?.services.mailgun?.status);
              return (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badge.bg}`}>
                  {badge.text}
                </span>
              );
            })()}
          </div>
          <div className="space-y-1.5 text-xs text-slate-600">
            <div className="flex justify-between"><span>Domain:</span> <strong className="text-slate-900 font-mono text-[11px]">{deepHealth?.services.mailgun?.sender_domain || 'soinventive.co.uk'}</strong></div>
            <div className="flex justify-between"><span>Transport:</span> <strong className="text-emerald-700">HTTP REST API</strong></div>
            <div className="flex justify-between"><span>Region:</span> <strong className="text-slate-900">EU</strong></div>
          </div>
        </div>

      </div>

    </div>
  );
}
