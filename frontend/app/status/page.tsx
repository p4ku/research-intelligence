"use client";

import React, { useState, useEffect } from 'react';
import { Activity, ShieldAlert, ArrowLeft, RefreshCw, Server, Cpu, Database } from 'lucide-react';

interface ServiceStatus {
  status: 'checking' | 'online' | 'offline';
  latency: number | null;
  statusCode: number | null;
  error: string | null;
}

const getApiUrl = (): string => {
  if (typeof window !== 'undefined') {
    if (window.location.hostname === 'sri.soinventive.co.uk') {
      return '/api/';
    }
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/';
};

const getMcpUrl = (): string => {
  if (typeof window !== 'undefined') {
    if (window.location.hostname === 'sri.soinventive.co.uk') {
      return '/sse';
    }
  }
  return process.env.NEXT_PUBLIC_MCP_URL || 'http://localhost:8001/sse';
};

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

  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const checkStatuses = async () => {
    setIsRefreshing(true);
    
    // Check API Status
    const apiStart = performance.now();
    try {
      const response = await fetch(getApiUrl(), {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      });
      const apiEnd = performance.now();
      setApiStatus({
        status: 'online',
        latency: Math.round(apiEnd - apiStart),
        statusCode: response.status,
        error: null,
      });
    } catch (err: any) {
      setApiStatus({
        status: 'offline',
        latency: null,
        statusCode: null,
        error: err.message || 'Network connection failed',
      });
    }

    // Check MCP Status
    const mcpStart = performance.now();
    try {
      const response = await fetch(getMcpUrl(), {
        method: 'GET',
      });
      const mcpEnd = performance.now();
      
      // Even if it returns 405 (Method Not Allowed) or 400, it means the server is online and responding
      setMcpStatus({
        status: 'online',
        latency: Math.round(mcpEnd - mcpStart),
        statusCode: response.status,
        error: null,
      });
    } catch (err: any) {
      setMcpStatus({
        status: 'offline',
        latency: null,
        statusCode: null,
        error: err.message || 'Network connection failed',
      });
    }

    setIsRefreshing(false);
  };

  useEffect(() => {
    checkStatuses();
  }, []);

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
      <div style={{ maxWidth: '800px', width: '100%' }}>
        {/* Navigation & Header */}
        <header style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '3rem',
        }}>
          <a href="/" style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            color: '#94a3b8',
            textDecoration: 'none',
            fontSize: '0.95rem',
            transition: 'color 0.2s',
          }}
             onMouseEnter={(e) => { e.currentTarget.style.color = '#38bdf8'; }}
             onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; }}
          >
            <ArrowLeft size={16} /> Back to dashboard
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
              padding: '0.5rem 1rem',
              borderRadius: '6px',
              color: '#f1f5f9',
              cursor: 'pointer',
              fontSize: '0.9rem',
              transition: 'background-color 0.2s, border-color 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#334155';
              e.currentTarget.style.borderColor = '#475569';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#1e293b';
              e.currentTarget.style.borderColor = '#334155';
            }}
          >
            <RefreshCw size={14} style={{
              animation: isRefreshing ? 'spin 1s linear infinite' : 'none'
            }} />
            {isRefreshing ? 'Refreshing...' : 'Refresh Status'}
          </button>
        </header>

        {/* Title */}
        <div style={{ textAlign: 'center', marginBottom: '4rem' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '64px',
            height: '64px',
            borderRadius: '16px',
            background: 'linear-gradient(135deg, #38bdf8 0%, #1d4ed8 100%)',
            boxShadow: '0 8px 24px rgba(56, 189, 248, 0.2)',
            marginBottom: '1.5rem',
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
            System Status
          </h1>
          <p style={{ color: '#94a3b8', marginTop: '0.5rem', fontSize: '1.1rem' }}>
            Real-time diagnostics of Schwarz Research Intelligence services
          </p>
        </div>

        {/* Status Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
          gap: '2rem',
          marginBottom: '3rem',
        }}>
          {/* Django API Card */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '2rem',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
            position: 'relative',
            overflow: 'hidden',
          }}>
            {/* Background Glow */}
            <div style={{
              position: 'absolute',
              top: 0,
              right: 0,
              width: '120px',
              height: '120px',
              borderRadius: '50%',
              background: apiStatus.status === 'online' 
                ? 'radial-gradient(circle, rgba(16,185,129,0.08) 0%, rgba(0,0,0,0) 70%)'
                : apiStatus.status === 'offline'
                  ? 'radial-gradient(circle, rgba(239,68,68,0.08) 0%, rgba(0,0,0,0) 70%)'
                  : 'radial-gradient(circle, rgba(245,158,11,0.08) 0%, rgba(0,0,0,0) 70%)',
              zIndex: 0,
            }} />

            <div style={{ position: 'relative', zIndex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <div style={{ color: '#38bdf8', display: 'flex', alignItems: 'center' }}><Database size={20} /></div>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: '700', margin: 0, color: '#f1f5f9' }}>Django REST API</h2>
                </div>
                
                {/* Status Badge */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.375rem',
                  padding: '0.25rem 0.75rem',
                  borderRadius: '9999px',
                  fontSize: '0.8rem',
                  fontWeight: '600',
                  textTransform: 'uppercase',
                  backgroundColor: apiStatus.status === 'online' 
                    ? 'rgba(16,185,129,0.1)' 
                    : apiStatus.status === 'offline' 
                      ? 'rgba(239,68,68,0.1)' 
                      : 'rgba(245,158,11,0.1)',
                  color: apiStatus.status === 'online' 
                    ? '#10b981' 
                    : apiStatus.status === 'offline' 
                      ? '#ef4444' 
                      : '#f59e0b',
                }}>
                  <span style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: 'currentColor',
                    display: 'inline-block',
                  }} />
                  {apiStatus.status}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', color: '#94a3b8', fontSize: '0.9rem' }}>
                <div>
                  <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>Endpoint URL</span>
                  <code style={{ color: '#cbd5e1', wordBreak: 'break-all' }}>{getApiUrl()}</code>
                </div>

                {apiStatus.status === 'online' && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', borderTop: '1px solid #1f2937', paddingTop: '1rem' }}>
                    <div>
                      <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>Latency</span>
                      <span style={{ fontSize: '1.2rem', color: '#f1f5f9', fontWeight: '600' }}>{apiStatus.latency} ms</span>
                    </div>
                    <div>
                      <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>HTTP Status</span>
                      <span style={{ fontSize: '1.2rem', color: '#f1f5f9', fontWeight: '600' }}>{apiStatus.statusCode}</span>
                    </div>
                  </div>
                )}

                {apiStatus.status === 'offline' && (
                  <div style={{
                    marginTop: '0.5rem',
                    padding: '0.75rem',
                    backgroundColor: 'rgba(239,68,68,0.05)',
                    border: '1px solid rgba(239,68,68,0.15)',
                    borderRadius: '6px',
                    color: '#f87171',
                    display: 'flex',
                    gap: '0.5rem',
                    alignItems: 'flex-start',
                  }}>
                    <ShieldAlert size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
                    <span>{apiStatus.error}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* MCP Server Card */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '2rem',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
            position: 'relative',
            overflow: 'hidden',
          }}>
            {/* Background Glow */}
            <div style={{
              position: 'absolute',
              top: 0,
              right: 0,
              width: '120px',
              height: '120px',
              borderRadius: '50%',
              background: mcpStatus.status === 'online' 
                ? 'radial-gradient(circle, rgba(16,185,129,0.08) 0%, rgba(0,0,0,0) 70%)'
                : mcpStatus.status === 'offline'
                  ? 'radial-gradient(circle, rgba(239,68,68,0.08) 0%, rgba(0,0,0,0) 70%)'
                  : 'radial-gradient(circle, rgba(245,158,11,0.08) 0%, rgba(0,0,0,0) 70%)',
              zIndex: 0,
            }} />

            <div style={{ position: 'relative', zIndex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <div style={{ color: '#38bdf8', display: 'flex', alignItems: 'center' }}><Cpu size={20} /></div>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: '700', margin: 0, color: '#f1f5f9' }}>FastMCP Server</h2>
                </div>
                
                {/* Status Badge */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.375rem',
                  padding: '0.25rem 0.75rem',
                  borderRadius: '9999px',
                  fontSize: '0.8rem',
                  fontWeight: '600',
                  textTransform: 'uppercase',
                  backgroundColor: mcpStatus.status === 'online' 
                    ? 'rgba(16,185,129,0.1)' 
                    : mcpStatus.status === 'offline' 
                      ? 'rgba(239,68,68,0.1)' 
                      : 'rgba(245,158,11,0.1)',
                  color: mcpStatus.status === 'online' 
                    ? '#10b981' 
                    : mcpStatus.status === 'offline' 
                      ? '#ef4444' 
                      : '#f59e0b',
                }}>
                  <span style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: 'currentColor',
                    display: 'inline-block',
                  }} />
                  {mcpStatus.status}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', color: '#94a3b8', fontSize: '0.9rem' }}>
                <div>
                  <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>SSE Transport URL</span>
                  <code style={{ color: '#cbd5e1', wordBreak: 'break-all' }}>{getMcpUrl()}</code>
                </div>

                {mcpStatus.status === 'online' && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', borderTop: '1px solid #1f2937', paddingTop: '1rem' }}>
                    <div>
                      <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>Latency</span>
                      <span style={{ fontSize: '1.2rem', color: '#f1f5f9', fontWeight: '600' }}>{mcpStatus.latency} ms</span>
                    </div>
                    <div>
                      <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>HTTP Status</span>
                      <span style={{ fontSize: '1.2rem', color: '#f1f5f9', fontWeight: '600' }}>{mcpStatus.statusCode}</span>
                    </div>
                  </div>
                )}

                {mcpStatus.status === 'offline' && (
                  <div style={{
                    marginTop: '0.5rem',
                    padding: '0.75rem',
                    backgroundColor: 'rgba(239,68,68,0.05)',
                    border: '1px solid rgba(239,68,68,0.15)',
                    borderRadius: '6px',
                    color: '#f87171',
                    display: 'flex',
                    gap: '0.5rem',
                    alignItems: 'flex-start',
                  }}>
                    <ShieldAlert size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
                    <span>{mcpStatus.error}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Additional Info Footer */}
        <div style={{
          backgroundColor: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: '12px',
          padding: '1.5rem 2rem',
          color: '#64748b',
          fontSize: '0.875rem',
          lineHeight: '1.5',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
        }}>
          <Server size={24} style={{ color: '#475569', flexShrink: 0 }} />
          <div>
            <strong>Architecture Check:</strong> Next.js frontend calls the backend REST API on the domain <code>sri.soinventive.co.uk</code>. The FastMCP model service acts as an orchestration middleware connected directly to the database and exposed via server-sent events (SSE).
          </div>
        </div>
      </div>

      {/* Embedded CSS Animations */}
      <style jsx global>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
