"use client";

import React, { useState, useEffect } from 'react';
import { Activity, ShieldAlert, ArrowLeft, RefreshCw, Server, Cpu, Database } from 'lucide-react';

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

  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const [apiUrl, setApiUrl] = useState<string>(
    (() => {
      const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/';
      const cleanBase = base.endsWith('/') ? base.slice(0, -1) : base;
      return `${cleanBase}/health/`;
    })()
  );
  const [mcpUrl, setMcpUrl] = useState<string>(
    process.env.NEXT_PUBLIC_MCP_URL || 'http://localhost:8001/sse'
  );

  const [showMcpGuide, setShowMcpGuide] = useState<boolean>(false);
  const [showApiGuide, setShowApiGuide] = useState<boolean>(false);

  const checkStatuses = async () => {
    setIsRefreshing(true);
    
    const targetApiUrl = typeof window !== 'undefined' && window.location.hostname === 'sri.soinventive.co.uk'
      ? '/api/health/'
      : (() => {
          const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/';
          const cleanBase = base.endsWith('/') ? base.slice(0, -1) : base;
          return `${cleanBase}/health/`;
        })();
      
    const targetMcpUrl = typeof window !== 'undefined' && window.location.hostname === 'sri.soinventive.co.uk'
      ? '/sse'
      : (process.env.NEXT_PUBLIC_MCP_URL || 'http://localhost:8001/sse');

    // Check API Status
    const apiStart = performance.now();
    try {
      const response = await fetch(targetApiUrl, {
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
      const response = await fetch(targetMcpUrl, {
        method: 'GET',
      });
      const mcpEnd = performance.now();
      
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
    if (typeof window !== 'undefined' && window.location.hostname === 'sri.soinventive.co.uk') {
      setApiUrl('/api/health/');
      setMcpUrl('/sse');
    }
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
                  <code style={{ color: '#cbd5e1', wordBreak: 'break-all' }}>{apiUrl}</code>
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
                  <code style={{ color: '#cbd5e1', wordBreak: 'break-all' }}>{mcpUrl}</code>
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

        {/* Integration Guides */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginBottom: '3rem' }}>
          {/* MCP Integration Guide */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            overflow: 'hidden',
            transition: 'border-color 0.2s',
          }}>
            <button 
              onClick={() => setShowMcpGuide(!showMcpGuide)}
              style={{
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '1.5rem 2rem',
                backgroundColor: 'transparent',
                border: 'none',
                color: '#f1f5f9',
                cursor: 'pointer',
                textAlign: 'left',
                fontSize: '1.1rem',
                fontWeight: '600',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Cpu size={18} style={{ color: '#0284c7' }} />
                <span>OpenCode MCP Integration Guide</span>
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
                padding: '0 2rem 2rem 2rem',
                borderTop: '1px solid #1f2937',
                paddingTop: '1.5rem',
                color: '#cbd5e1',
                fontSize: '0.9rem',
                lineHeight: '1.6',
              }}>
                <p style={{ margin: '0 0 1rem 0' }}>
                  To register this remote MCP server inside your <strong>OpenCode</strong> editor environment, append the server configuration to your OpenCode settings file:
                </p>
                <div style={{ marginBottom: '1.5rem' }}>
                  <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>Settings file path</span>
                  <pre style={{
                    margin: 0,
                    padding: '0.75rem 1rem',
                    backgroundColor: '#030712',
                    border: '1px solid #1f2937',
                    borderRadius: '6px',
                    color: '#38bdf8',
                    fontFamily: 'monospace',
                    fontSize: '0.85rem',
                  }}>nano ~/.config/opencode/opencode.json</pre>
                </div>
                
                <div>
                  <span style={{ display: 'block', color: '#475569', fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: '600', marginBottom: '0.25rem' }}>Add under "mcpServers" key</span>
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
  "url": "${mcpUrl}",
  "headers": {
    "X-API-KEY-ID": "your_mcp_key_id",
    "X-API-SECRET": "your_mcp_secret"
  },
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
            transition: 'border-color 0.2s',
          }}>
            <button 
              onClick={() => setShowApiGuide(!showApiGuide)}
              style={{
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '1.5rem 2rem',
                backgroundColor: 'transparent',
                border: 'none',
                color: '#f1f5f9',
                cursor: 'pointer',
                textAlign: 'left',
                fontSize: '1.1rem',
                fontWeight: '600',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Database size={18} style={{ color: '#0284c7' }} />
                <span>REST API Integration Guide</span>
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
                padding: '0 2rem 2rem 2rem',
                borderTop: '1px solid #1f2937',
                paddingTop: '1.5rem',
                color: '#cbd5e1',
                fontSize: '0.9rem',
                lineHeight: '1.6',
              }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                  <div>
                    <h3 style={{ fontSize: '1rem', color: '#f1f5f9', margin: '0 0 0.5rem 0', fontWeight: '600' }}>1. Authenticate & Obtain JWT Token</h3>
                    <p style={{ margin: '0 0 0.75rem 0' }}>
                      Exchange user credentials for an access and refresh token pair:
                    </p>
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
  -d '{"username": "admin", "password": "your_password"}'`}</pre>
                    <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.8rem', color: '#64748b' }}>
                      Response returns json payload: <code>{`{ "access": "...", "refresh": "..." }`}</code>.
                    </p>
                  </div>

                  <div>
                    <h3 style={{ fontSize: '1rem', color: '#f1f5f9', margin: '0 0 0.5rem 0', fontWeight: '600' }}>2. Request Protected Resources</h3>
                    <p style={{ margin: '0 0 0.75rem 0' }}>
                      Include the retrieved access token as a Bearer token in the <code>Authorization</code> header:
                    </p>
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
                    }}>{`curl -X GET ${apiUrl}workspaces/ \\
  -H "Authorization: Bearer <your_access_token>"`}</pre>
                  </div>

                  <div>
                    <h3 style={{ fontSize: '1rem', color: '#f1f5f9', margin: '0 0 0.5rem 0', fontWeight: '600' }}>3. Refresh Token</h3>
                    <p style={{ margin: '0 0 0.75rem 0' }}>
                      Renew the access token using the refresh token before it expires:
                    </p>
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
                    }}>{`curl -X POST ${apiUrl.replace(/\/$/, '')}/auth/refresh/ \\
  -H "Content-Type: application/json" \\
  -d '{"refresh": "<your_refresh_token>"}'`}</pre>
                  </div>
                </div>
              </div>
            )}
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
