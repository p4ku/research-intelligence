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

  const [apiUrl, setApiUrl] = useState<string>('http://localhost:8000/api/health/');
  const [mcpUrl, setMcpUrl] = useState<string>('http://localhost:8001/sse');

  const [showMcpGuide, setShowMcpGuide] = useState<boolean>(false);
  const [showApiGuide, setShowApiGuide] = useState<boolean>(false);

  const checkStatuses = async () => {
    setIsRefreshing(true);
    const { targetApiUrl, targetDiagnosticsUrl, targetMcpUrl, displayApiUrl, displayMcpUrl } = getEndpoints();
    setApiUrl(displayApiUrl);
    setMcpUrl(displayMcpUrl);

    const apiStart = performance.now();
    const mcpStart = performance.now();

    // Execute all probes concurrently without blocking UI
    const [apiRes, mcpRes, diagRes] = await Promise.allSettled([
      fetch(targetApiUrl, { method: 'GET', headers: { 'Accept': 'application/json' } }),
      fetch(targetMcpUrl, { method: 'GET' }),
      fetch(targetDiagnosticsUrl, { method: 'GET', headers: { 'Accept': 'application/json' } }),
    ]);

    // 1. Process API Liveness Probe
    if (apiRes.status === 'fulfilled') {
      const apiEnd = performance.now();
      const isOk = apiRes.value.ok;
      let errorMsg: string | null = null;
      if (!isOk) {
        errorMsg = `Server unreachable / Error (HTTP ${apiRes.value.status})`;
      }
      setApiStatus({
        status: isOk ? 'online' : 'offline',
        latency: isOk ? Math.round(apiEnd - apiStart) : null,
        statusCode: apiRes.value.status,
        error: errorMsg,
      });
    } else {
      setApiStatus({
        status: 'offline',
        latency: null,
        statusCode: null,
        error: 'Network connection failed / Service offline',
      });
    }

    // 2. Process MCP SSE Probe
    if (mcpRes.status === 'fulfilled') {
      const mcpEnd = performance.now();
      const isMcpOk = mcpRes.value.ok || mcpRes.value.status === 401 || mcpRes.value.status === 400;
      setMcpStatus({
        status: isMcpOk ? 'online' : 'offline',
        latency: Math.round(mcpEnd - mcpStart),
        statusCode: mcpRes.value.status,
        error: isMcpOk ? null : `HTTP ${mcpRes.value.status}`,
      });
    } else {
      setMcpStatus({
        status: 'offline',
        latency: null,
        statusCode: null,
        error: 'FastMCP SSE unreachable',
      });
    }

    // 3. Process Deep Diagnostics Probes
    if (diagRes.status === 'fulfilled') {
      const ct = diagRes.value.headers.get('content-type') || '';
      if (diagRes.value.ok && ct.includes('application/json')) {
        try {
          const data: DeepHealthData = await diagRes.value.json();
          setDeepHealth(data);
        } catch {
          setDeepHealth(null);
        }
      } else {
        setDeepHealth(null);
      }
    } else {
      setDeepHealth(null);
    }

    setIsRefreshing(false);
  };

  useEffect(() => {
    const { displayApiUrl, displayMcpUrl } = getEndpoints();
    setApiUrl(displayApiUrl);
    setMcpUrl(displayMcpUrl);
    checkStatuses();
  }, []);

  const getBadge = (serviceStatus?: string) => {
    if (isRefreshing) {
      return { text: 'PROBING...', bg: 'rgba(56,189,248,0.1)', color: '#38bdf8' };
    }
    if (!serviceStatus || serviceStatus === 'offline' || !deepHealth) {
      return { text: 'OFFLINE', bg: 'rgba(239,68,68,0.1)', color: '#ef4444' };
    }
    if (serviceStatus === 'online' || serviceStatus === 'configured') {
      return { text: serviceStatus.toUpperCase(), bg: 'rgba(16,185,129,0.1)', color: '#10b981' };
    }
    return { text: serviceStatus.toUpperCase(), bg: 'rgba(245,158,11,0.1)', color: '#f59e0b' };
  };

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#090d16',
      backgroundImage: 'radial-gradient(circle at 50% 10%, #1e1b4b 0%, #090d16 60%)',
      color: '#f8fafc',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: '2rem 1rem',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
    }}>
      <div style={{ maxWidth: '1000px', width: '100%' }}>
        {/* Navigation & Header */}
        <header style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '2.5rem',
        }}>
          <a href="/" style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            color: '#94a3b8',
            textDecoration: 'none',
            fontSize: '0.95rem',
            fontWeight: '500',
            transition: 'color 0.2s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#f1f5f9'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; }}
          >
            <ArrowLeft size={16} />
            Back to dashboard
          </a>

          <button 
            onClick={checkStatuses}
            disabled={isRefreshing}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              padding: '0.625rem 1.25rem',
              borderRadius: '8px',
              color: '#f1f5f9',
              cursor: isRefreshing ? 'not-allowed' : 'pointer',
              fontSize: '0.9rem',
              fontWeight: '600',
              boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
              transition: 'background-color 0.2s, border-color 0.2s',
            }}
            onMouseEnter={(e) => {
              if (!isRefreshing) {
                e.currentTarget.style.backgroundColor = '#334155';
                e.currentTarget.style.borderColor = '#475569';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#1e293b';
              e.currentTarget.style.borderColor = '#334155';
            }}
          >
            <RefreshCw size={15} style={{
              animation: isRefreshing ? 'spin 1s linear infinite' : 'none'
            }} />
            {isRefreshing ? 'Running Probes...' : 'Run Diagnostics'}
          </button>
        </header>

        {/* Title */}
        <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '64px',
            height: '64px',
            borderRadius: '16px',
            background: 'linear-gradient(135deg, #38bdf8 0%, #1d4ed8 100%)',
            boxShadow: '0 8px 24px rgba(56, 189, 248, 0.2)',
            marginBottom: '1.25rem',
          }}>
            <Activity size={32} color="#ffffff" />
          </div>
          <h1 style={{
            fontSize: '2.5rem',
            fontWeight: '800',
            letterSpacing: '-0.025em',
            margin: 0,
            background: 'linear-gradient(to right, #f8fafc, #94a3b8)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>
            Infrastructure Diagnostics
          </h1>
          <p style={{ color: '#94a3b8', marginTop: '0.5rem', fontSize: '1.1rem' }}>
            Real-time live health probes across Database, Redis, Celery Workers, S3 Storage, LLM Providers, FastMCP, and Mailgun
          </p>
        </div>

        {/* Top Status Overview Cards (Primary Services) */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: '1.5rem',
          marginBottom: '2.5rem',
        }}>
          {/* Django API Card */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.75rem',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
            position: 'relative',
            overflow: 'hidden',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <div style={{ color: '#38bdf8' }}><Server size={22} /></div>
                <h2 style={{ fontSize: '1.2rem', fontWeight: '700', margin: 0, color: '#f1f5f9' }}>Django REST API</h2>
              </div>
              
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.375rem',
                padding: '0.25rem 0.75rem',
                borderRadius: '9999px',
                fontSize: '0.8rem',
                fontWeight: '700',
                textTransform: 'uppercase',
                backgroundColor: apiStatus.status === 'online' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                color: apiStatus.status === 'online' ? '#10b981' : '#ef4444',
              }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'currentColor' }} />
                {apiStatus.status}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', color: '#94a3b8', fontSize: '0.875rem' }}>
              <div>
                <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600' }}>Endpoint URL</span>
                <code style={{ color: '#cbd5e1', wordBreak: 'break-all' }}>{apiUrl}</code>
              </div>

              {apiStatus.status === 'online' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', borderTop: '1px solid #1f2937', paddingTop: '0.75rem' }}>
                  <div>
                    <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600' }}>Latency</span>
                    <span style={{ fontSize: '1.1rem', color: '#f1f5f9', fontWeight: '600' }}>{apiStatus.latency} ms</span>
                  </div>
                  <div>
                    <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600' }}>HTTP Status</span>
                    <span style={{ fontSize: '1.1rem', color: '#10b981', fontWeight: '600' }}>{apiStatus.statusCode} OK</span>
                  </div>
                </div>
              )}

              {apiStatus.status === 'offline' && (
                <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: '6px', color: '#f87171' }}>
                  <ShieldAlert size={16} style={{ display: 'inline', marginRight: '0.5rem' }} />
                  {apiStatus.error || 'Backend service unreachable'}
                </div>
              )}
            </div>
          </div>

          {/* FastMCP Server Card */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.75rem',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
            position: 'relative',
            overflow: 'hidden',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <div style={{ color: '#38bdf8' }}><Cpu size={22} /></div>
                <h2 style={{ fontSize: '1.2rem', fontWeight: '700', margin: 0, color: '#f1f5f9' }}>FastMCP Server (SSE)</h2>
              </div>
              
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.375rem',
                padding: '0.25rem 0.75rem',
                borderRadius: '9999px',
                fontSize: '0.8rem',
                fontWeight: '700',
                textTransform: 'uppercase',
                backgroundColor: mcpStatus.status === 'online' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                color: mcpStatus.status === 'online' ? '#10b981' : '#ef4444',
              }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'currentColor' }} />
                {mcpStatus.status}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', color: '#94a3b8', fontSize: '0.875rem' }}>
              <div>
                <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600' }}>SSE Transport URL</span>
                <code style={{ color: '#cbd5e1', wordBreak: 'break-all' }}>{mcpUrl}</code>
              </div>

              {mcpStatus.status === 'online' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', borderTop: '1px solid #1f2937', paddingTop: '0.75rem' }}>
                  <div>
                    <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600' }}>Latency</span>
                    <span style={{ fontSize: '1.1rem', color: '#f1f5f9', fontWeight: '600' }}>{mcpStatus.latency} ms</span>
                  </div>
                  <div>
                    <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600' }}>Protocol</span>
                    <span style={{ fontSize: '1.1rem', color: '#38bdf8', fontWeight: '600' }}>SSE Ready</span>
                  </div>
                </div>
              )}

              {mcpStatus.status === 'offline' && (
                <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: '6px', color: '#f87171' }}>
                  <ShieldAlert size={16} style={{ display: 'inline', marginRight: '0.5rem' }} />
                  {mcpStatus.error || 'MCP SSE service unreachable'}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Deep Infrastructure Diagnostics Grid */}
        <h2 style={{ fontSize: '1.4rem', fontWeight: '700', color: '#f1f5f9', marginBottom: '1.25rem' }}>
          Backend Infrastructure Probes
        </h2>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1.5rem',
          marginBottom: '3rem',
        }}>
          {/* 1. PostgreSQL Database */}
          <div style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '10px',
            padding: '1.5rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                <Database size={18} color="#38bdf8" />
                <span style={{ fontWeight: '600', color: '#f8fafc' }}>PostgreSQL</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.database?.status);
                return (
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: '700',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: badge.bg,
                    color: badge.color,
                  }}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Engine / Vendor:</span>
                <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.database?.vendor?.toUpperCase() || 'POSTGRESQL'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Query Latency:</span>
                <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.database?.latency_ms ? `${deepHealth.services.database.latency_ms} ms` : '-'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Workspaces / Papers:</span>
                <strong style={{ color: '#38bdf8' }}>
                  {deepHealth?.services.database?.counts?.workspaces ?? 0} ws / {deepHealth?.services.database?.counts?.papers ?? 0} papers
                </strong>
              </div>
            </div>
          </div>

          {/* 2. Redis Broker */}
          <div style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '10px',
            padding: '1.5rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                <Zap size={18} color="#f59e0b" />
                <span style={{ fontWeight: '600', color: '#f8fafc' }}>Redis Cache & TLS</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.redis?.status);
                return (
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: '700',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: badge.bg,
                    color: badge.color,
                  }}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Protocol / Scheme:</span>
                <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.redis?.scheme?.toUpperCase() || 'REDISS (TLS)'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Ping Probe Latency:</span>
                <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.redis?.latency_ms ? `${deepHealth.services.redis.latency_ms} ms` : '-'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Task Broker Status:</span>
                <strong style={{ color: deepHealth?.services.redis?.status === 'online' ? '#10b981' : '#94a3b8' }}>
                  {deepHealth?.services.redis?.status === 'online' ? 'Connected' : 'Disconnected'}
                </strong>
              </div>
            </div>
          </div>

          {/* 3. Celery Asynchronous Workers */}
          <div style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '10px',
            padding: '1.5rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                <Cpu size={18} color="#a855f7" />
                <span style={{ fontWeight: '600', color: '#f8fafc' }}>Celery Workers</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.celery?.status);
                return (
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: '700',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: badge.bg,
                    color: badge.color,
                  }}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Execution Mode:</span>
                <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.celery?.mode || 'Distributed Worker'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Task Roundtrip:</span>
                <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.celery?.latency_ms ? `${deepHealth.services.celery.latency_ms} ms` : '-'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Live Task Result:</span>
                <strong style={{ color: deepHealth?.services.celery?.result ? '#10b981' : '#f59e0b' }}>
                  {deepHealth?.services.celery?.result ? 'PONG (Task Verified)' : (deepHealth ? 'No worker response' : '-')}
                </strong>
              </div>
            </div>
          </div>

          {/* 4. S3 / Object Storage */}
          <div style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '10px',
            padding: '1.5rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                <HardDrive size={18} color="#10b981" />
                <span style={{ fontWeight: '600', color: '#f8fafc' }}>S3 Object Storage</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.storage?.status);
                return (
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: '700',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: badge.bg,
                    color: badge.color,
                  }}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Storage Backend:</span>
                <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.storage?.backend?.toUpperCase() || 'S3'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Bucket Name:</span>
                <strong style={{ color: '#38bdf8' }}>{deepHealth?.services.storage?.bucket || 'bucket-sri-production'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Write/Read/Delete Test:</span>
                <strong style={{ color: deepHealth?.services.storage?.verified ? '#10b981' : '#94a3b8' }}>
                  {deepHealth?.services.storage?.verified ? `Verified (${deepHealth.services.storage.latency_ms} ms)` : '-'}
                </strong>
              </div>
            </div>
          </div>

          {/* 5. Mailgun Email Gateway */}
          <div style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '10px',
            padding: '1.5rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                <Mail size={18} color="#ec4899" />
                <span style={{ fontWeight: '600', color: '#f8fafc' }}>Mailgun Email API</span>
              </div>
              {(() => {
                const badge = getBadge(deepHealth?.services.mailgun?.status);
                return (
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: '700',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: badge.bg,
                    color: badge.color,
                  }}>
                    {badge.text}
                  </span>
                );
              })()}
            </div>

            <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Sender Domain:</span>
                <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.mailgun?.sender_domain || 'soinventive.co.uk'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>API Endpoint:</span>
                <strong style={{ color: '#e2e8f0' }}>api.eu.mailgun.net/v3</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Notification Digest:</span>
                <strong style={{ color: deepHealth?.services.mailgun?.status === 'configured' ? '#10b981' : '#94a3b8' }}>
                  {deepHealth?.services.mailgun?.status === 'configured' ? 'Executive Reports Ready' : 'Unconfigured'}
                </strong>
              </div>
            </div>
          </div>
        </div>

        {/* AI & LLM Model Providers Panel */}
        <div style={{ marginBottom: '3rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
            <Sparkles size={22} color="#38bdf8" />
            <h2 style={{ fontSize: '1.4rem', fontWeight: '700', color: '#f1f5f9', margin: 0 }}>
              AI & LLM Model Providers
            </h2>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '1.5rem',
          }}>
            {/* Google Vertex AI / GenAI Subpanel */}
            <div style={{
              backgroundColor: '#0f172a',
              border: '1px solid #1e293b',
              borderRadius: '12px',
              padding: '1.75rem',
              position: 'relative',
              overflow: 'hidden',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <Bot size={20} color="#38bdf8" />
                  <div>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: '700', margin: 0, color: '#f8fafc' }}>Google Vertex AI</h3>
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Primary Multimodal Reasoning Engine</span>
                  </div>
                </div>

                {(() => {
                  const badge = getBadge(deepHealth?.services.llm_providers?.google?.status);
                  return (
                    <span style={{
                      fontSize: '0.75rem',
                      fontWeight: '700',
                      padding: '0.25rem 0.625rem',
                      borderRadius: '9999px',
                      backgroundColor: badge.bg,
                      color: badge.color,
                      textTransform: 'uppercase',
                    }}>
                      {badge.text}
                    </span>
                  );
                })()}
              </div>

              <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Active Target Model:</span>
                  <strong style={{ color: '#38bdf8' }}>{deepHealth?.services.llm_providers?.google?.model || 'gemini-3.7-flash'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Data Sovereignty Region:</span>
                  <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.llm_providers?.google?.location?.toUpperCase() || 'EU'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Inference Latency:</span>
                  <strong style={{ color: '#e2e8f0' }}>{deepHealth?.services.llm_providers?.google?.latency_ms ? `${deepHealth.services.llm_providers.google.latency_ms} ms` : '-'}</strong>
                </div>
                
                {deepHealth?.services.llm_providers?.google?.service_account_email && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Service Account:</span>
                    <strong style={{ color: '#cbd5e1', fontSize: '0.8rem', wordBreak: 'break-all' }}>
                      {deepHealth.services.llm_providers.google.service_account_email}
                    </strong>
                  </div>
                )}

                {deepHealth?.services.llm_providers?.google?.sample_response && (
                  <div style={{ marginTop: '0.5rem', padding: '0.75rem', backgroundColor: '#030712', border: '1px solid #1f2937', borderRadius: '6px' }}>
                    <span style={{ display: 'block', color: '#475569', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>Live Verification Probe Response</span>
                    <code style={{ color: '#34d399', fontSize: '0.8rem' }}>"{deepHealth.services.llm_providers.google.sample_response}"</code>
                  </div>
                )}

                {deepHealth?.services.llm_providers?.google?.error && (
                  <div style={{ marginTop: '0.5rem', padding: '0.75rem', backgroundColor: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: '6px', color: '#f87171', fontSize: '0.8rem' }}>
                    <ShieldAlert size={14} style={{ display: 'inline', marginRight: '0.375rem' }} />
                    {deepHealth.services.llm_providers.google.error}
                  </div>
                )}
              </div>
            </div>

            {/* OpenRouter Subpanel (Future Gateway) */}
            <div style={{
              backgroundColor: '#0f172a',
              border: '1px solid #1e293b',
              borderRadius: '12px',
              padding: '1.75rem',
              position: 'relative',
              overflow: 'hidden',
              opacity: 0.85,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <Globe size={20} color="#a855f7" />
                  <div>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: '700', margin: 0, color: '#f8fafc' }}>OpenRouter Gateway</h3>
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Multi-Model Fallback Gateway</span>
                  </div>
                </div>

                <span style={{
                  fontSize: '0.75rem',
                  fontWeight: '700',
                  padding: '0.25rem 0.625rem',
                  borderRadius: '9999px',
                  backgroundColor: deepHealth?.services.llm_providers?.openrouter?.status === 'configured' ? 'rgba(16,185,129,0.1)' : 'rgba(100,116,139,0.15)',
                  color: deepHealth?.services.llm_providers?.openrouter?.status === 'configured' ? '#10b981' : '#94a3b8',
                  textTransform: 'uppercase',
                }}>
                  {deepHealth?.services.llm_providers?.openrouter?.status === 'configured' ? 'CONFIGURED' : 'STANDBY'}
                </span>
              </div>

              <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Supported Targets:</span>
                  <strong style={{ color: '#cbd5e1' }}>Claude 3.5 Sonnet, DeepSeek R1</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Integration Status:</span>
                  <strong style={{ color: '#94a3b8' }}>Secondary Provider (Planned)</strong>
                </div>
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.8rem', color: '#64748b', lineHeight: '1.4' }}>
                  OpenRouter will provide redundant multi-cloud routing across Anthropic and open-weights models once enabled.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Integration Guides Accordion */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginBottom: '3rem' }}>
          {/* MCP Integration Guide */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            overflow: 'hidden',
          }}>
            <button 
              onClick={() => setShowMcpGuide(!showMcpGuide)}
              style={{
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '1.25rem 1.75rem',
                backgroundColor: 'transparent',
                border: 'none',
                color: '#f1f5f9',
                cursor: 'pointer',
                textAlign: 'left',
                fontSize: '1.05rem',
                fontWeight: '600',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Cpu size={18} style={{ color: '#0284c7' }} />
                <span>OpenCode & Cursor MCP Integration Guide</span>
              </div>
              <span style={{
                color: '#94a3b8',
                transform: showMcpGuide ? 'rotate(180deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s',
                display: 'inline-block',
                fontSize: '0.8rem',
              }}>▼</span>
            </button>
            
            {showMcpGuide && (
              <div style={{
                padding: '0 1.75rem 1.75rem 1.75rem',
                borderTop: '1px solid #1f2937',
                paddingTop: '1.25rem',
                color: '#cbd5e1',
                fontSize: '0.9rem',
                lineHeight: '1.6',
              }}>
                <p style={{ margin: '0 0 1rem 0' }}>
                  Register this remote FastMCP server in your <strong>OpenCode</strong> or <strong>Cursor</strong> configuration:
                </p>
                
                <div>
                  <pre style={{
                    margin: 0,
                    padding: '1.25rem',
                    backgroundColor: '#030712',
                    border: '1px solid #1f2937',
                    borderRadius: '6px',
                    color: '#34d399',
                    fontFamily: 'monospace',
                    fontSize: '0.85rem',
                    overflowX: 'auto',
                    whiteSpace: 'pre',
                  }}>{`"schwarz-research-intelligence": {
  "type": "remote",
  "url": "${mcpUrl}?api_key_id=your_mcp_key_id&api_secret=your_mcp_secret",
  "enabled": true,
  "oauth": false
}`}</pre>
                </div>
              </div>
            )}
          </div>

          {/* API Integration Guide */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            overflow: 'hidden',
          }}>
            <button 
              onClick={() => setShowApiGuide(!showApiGuide)}
              style={{
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '1.25rem 1.75rem',
                backgroundColor: 'transparent',
                border: 'none',
                color: '#f1f5f9',
                cursor: 'pointer',
                textAlign: 'left',
                fontSize: '1.05rem',
                fontWeight: '600',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Database size={18} style={{ color: '#0284c7' }} />
                <span>Django REST API Authentication Guide</span>
              </div>
              <span style={{
                color: '#94a3b8',
                transform: showApiGuide ? 'rotate(180deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s',
                display: 'inline-block',
                fontSize: '0.8rem',
              }}>▼</span>
            </button>
            
            {showApiGuide && (
              <div style={{
                padding: '0 1.75rem 1.75rem 1.75rem',
                borderTop: '1px solid #1f2937',
                paddingTop: '1.25rem',
                color: '#cbd5e1',
                fontSize: '0.9rem',
                lineHeight: '1.6',
              }}>
                <pre style={{
                  margin: 0,
                  padding: '1rem',
                  backgroundColor: '#030712',
                  border: '1px solid #1f2937',
                  borderRadius: '6px',
                  color: '#cbd5e1',
                  fontFamily: 'monospace',
                  fontSize: '0.85rem',
                  overflowX: 'auto',
                }}>{`curl -X POST ${apiUrl.replace(/\/$/, '')}/auth/login/ \\
  -H "Content-Type: application/json" \\
  -d '{"api_key": "your_key_id:your_secret", "workspace_id": "your_workspace_uuid"}'`}</pre>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          backgroundColor: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: '12px',
          padding: '1.25rem 1.75rem',
          color: '#64748b',
          fontSize: '0.85rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
        }}>
          <Server size={20} style={{ color: '#475569', flexShrink: 0 }} />
          <div>
            <strong>Automated SLR & Intelligence Engine:</strong> All microservices are active on STACKIT Cloud Foundry.
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
