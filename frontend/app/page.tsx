"use client";

import React, { useState, useEffect } from 'react';
import { useAuth } from '../lib/auth/auth-context';
import ProtectedRoute from '../components/auth/ProtectedRoute';
import { workspaceService, WorkspaceItem } from '../lib/services/workspace-service';
import { 
  Layers, 
  Sparkles, 
  Cpu, 
  Search, 
  FileText, 
  Activity, 
  RefreshCw, 
  CheckCircle, 
  AlertCircle, 
  Plus, 
  ArrowRight,
  ShieldCheck,
  Zap,
  Globe,
  Sliders,
  DollarSign,
  ShieldAlert,
  UserCheck
} from 'lucide-react';

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <DashboardContent />
    </ProtectedRoute>
  );
}

function DashboardContent() {
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
      return { label: 'Admin', icon: '👑', bg: 'rgba(234, 179, 8, 0.15)', color: '#facc15', border: 'rgba(234, 179, 8, 0.3)' };
    }
    if (r === 'manager') {
      return { label: 'Manager', icon: '🛡️', bg: 'rgba(168, 85, 247, 0.15)', color: '#c084fc', border: 'rgba(168, 85, 247, 0.3)' };
    }
    return { label: 'Researcher', icon: '🔬', bg: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: 'rgba(56, 189, 248, 0.3)' };
  };

  return (
    <div style={{
      minHeight: 'calc(100vh - 65px)',
      backgroundColor: '#090d16',
      backgroundImage: 'radial-gradient(circle at 50% 10%, #1e1b4b 0%, #090d16 60%)',
      color: '#f8fafc',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: '2.5rem 1.5rem',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
    }}>
      <div style={{ maxWidth: '1100px', width: '100%' }}>
        
        {/* Welcome Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '2.5rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}>
          <div>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              backgroundColor: 'rgba(56, 189, 248, 0.1)',
              border: '1px solid rgba(56, 189, 248, 0.2)',
              borderRadius: '9999px',
              padding: '0.3rem 0.8rem',
              fontSize: '0.8rem',
              fontWeight: '600',
              color: '#38bdf8',
              marginBottom: '0.75rem',
            }}>
              <ShieldCheck size={14} />
              Logged in as {user?.is_superuser ? 'Superuser' : (user?.email || user?.username)}
            </div>
            <h1 style={{
              fontSize: '2.25rem',
              fontWeight: '800',
              letterSpacing: '-0.025em',
              margin: '0 0 0.5rem 0',
              background: 'linear-gradient(to right, #f8fafc, #94a3b8)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>
              Welcome back, {user?.first_name || user?.username}!
            </h1>
            <p style={{ color: '#94a3b8', margin: 0, fontSize: '1.05rem' }}>
              Your assigned systematic literature review projects and intelligence workspaces.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              onClick={fetchWorkspaces}
              disabled={isLoading}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                padding: '0.625rem 1.1rem',
                borderRadius: '8px',
                color: '#f1f5f9',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem',
                fontWeight: '600',
                transition: 'background-color 0.2s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#334155'; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#1e293b'; }}
            >
              <RefreshCw size={15} style={{ animation: isLoading ? 'spin 1s linear infinite' : 'none' }} />
              Refresh
            </button>

            <a
              href="/status"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                backgroundColor: 'rgba(56, 189, 248, 0.1)',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                padding: '0.625rem 1.1rem',
                borderRadius: '8px',
                color: '#38bdf8',
                textDecoration: 'none',
                fontSize: '0.875rem',
                fontWeight: '600',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(56, 189, 248, 0.2)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'rgba(56, 189, 248, 0.1)'; }}
            >
              <Activity size={15} />
              System Diagnostics
            </a>
          </div>
        </div>

        {/* Quick KPI Overview Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1.25rem',
          marginBottom: '2.5rem',
        }}>
          {/* Card 1: Accessible Workspaces */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.25rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <span style={{ fontSize: '0.85rem', color: '#94a3b8', fontWeight: '500' }}>Accessible Workspaces</span>
              <Layers size={18} color="#38bdf8" />
            </div>
            <div style={{ fontSize: '1.8rem', fontWeight: '800', color: '#f8fafc' }}>
              {workspaces.length}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
              Role-based tenant memberships
            </div>
          </div>

          {/* Card 2: AI Reasoning Engine */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.25rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <span style={{ fontSize: '0.85rem', color: '#94a3b8', fontWeight: '500' }}>Screening Engine</span>
              <Cpu size={18} color="#a855f7" />
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: '800', color: '#c084fc' }}>
              Gemini 3.7 Flash
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
              Google Vertex AI (EU Sovereign)
            </div>
          </div>

          {/* Card 3: Ingestion Sources */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.25rem',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <span style={{ fontSize: '0.85rem', color: '#94a3b8', fontWeight: '500' }}>Scrapers & Ingestion</span>
              <Globe size={18} color="#10b981" />
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: '800', color: '#34d399' }}>
              ArXiv, OpenAlex, Lens
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>
              Multi-source deduplication active
            </div>
          </div>
        </div>

        {/* Search & Filter Bar */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.5rem',
          gap: '1rem',
          flexWrap: 'wrap',
        }}>
          <h2 style={{ fontSize: '1.35rem', fontWeight: '700', margin: 0, color: '#f1f5f9' }}>
            Your SLR Workspaces ({filteredWorkspaces.length})
          </h2>

          <div style={{ position: 'relative', minWidth: '280px' }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, role, or criteria..."
              style={{
                width: '100%',
                backgroundColor: '#111827',
                border: '1px solid #1f2937',
                borderRadius: '8px',
                padding: '0.6rem 1rem 0.6rem 2.25rem',
                color: '#f8fafc',
                fontSize: '0.875rem',
                outline: 'none',
                boxSizing: 'border-box',
              }}
              onFocus={(e) => { e.currentTarget.style.borderColor = '#38bdf8'; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = '#1f2937'; }}
            />
            <Search size={15} color="#64748b" style={{
              position: 'absolute',
              left: '10px',
              top: '50%',
              transform: 'translateY(-50%)',
            }} />
          </div>
        </div>

        {/* Error banner if any */}
        {error && (
          <div style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            borderRadius: '10px',
            padding: '1rem',
            color: '#f87171',
            marginBottom: '2rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
          }}>
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* Workspaces Grid */}
        {isLoading && workspaces.length === 0 ? (
          <div style={{
            padding: '4rem',
            textAlign: 'center',
            color: '#94a3b8',
            backgroundColor: '#111827',
            borderRadius: '12px',
            border: '1px solid #1f2937',
          }}>
            <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', marginBottom: '1rem', color: '#38bdf8' }} />
            <div>Loading your workspace registry...</div>
          </div>
        ) : filteredWorkspaces.length === 0 ? (
          <div style={{
            padding: '4rem 2rem',
            textAlign: 'center',
            backgroundColor: '#111827',
            borderRadius: '12px',
            border: '1px solid #1f2937',
            color: '#94a3b8',
          }}>
            <Layers size={40} color="#475569" style={{ marginBottom: '1rem' }} />
            <h3 style={{ fontSize: '1.2rem', color: '#f1f5f9', margin: '0 0 0.5rem 0' }}>No workspaces found</h3>
            <p style={{ maxWidth: '480px', margin: '0 auto 1.5rem auto', fontSize: '0.9rem', lineHeight: '1.5' }}>
              {searchQuery 
                ? `No workspaces match "${searchQuery}". Try a different search term.` 
                : "You don't have any workspaces assigned yet. Create one via the REST API or FastMCP agent interface."}
            </p>
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '1.5rem',
          }}>
            {filteredWorkspaces.map((ws) => {
              const roleBadge = getRoleBadge(ws.user_role);
              return (
                <div
                  key={ws.id}
                  style={{
                    backgroundColor: '#111827',
                    border: '1px solid #1f2937',
                    borderRadius: '14px',
                    padding: '1.75rem',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                    transition: 'border-color 0.2s, transform 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#38bdf8';
                    e.currentTarget.style.transform = 'translateY(-2px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = '#1f2937';
                    e.currentTarget.style.transform = 'translateY(0)';
                  }}
                >
                  <div>
                    {/* Role & Model Header */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <span style={{
                        fontSize: '0.75rem',
                        fontWeight: '700',
                        padding: '0.2rem 0.55rem',
                        borderRadius: '6px',
                        backgroundColor: roleBadge.bg,
                        color: roleBadge.color,
                        border: `1px solid ${roleBadge.border}`,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                        textTransform: 'uppercase',
                        letterSpacing: '0.025em',
                      }}>
                        <span>{roleBadge.icon}</span>
                        <span>{roleBadge.label}</span>
                      </span>

                      <span style={{
                        fontSize: '0.7rem',
                        fontWeight: '700',
                        padding: '0.2rem 0.5rem',
                        borderRadius: '4px',
                        backgroundColor: 'rgba(56, 189, 248, 0.1)',
                        color: '#38bdf8',
                        textTransform: 'uppercase',
                      }}>
                        {ws.screening_llm_model || 'gemini-3.7-flash'}
                      </span>
                    </div>

                    {/* Workspace Title */}
                    <h3 style={{
                      fontSize: '1.25rem',
                      fontWeight: '700',
                      color: '#f8fafc',
                      margin: '0 0 0.875rem 0',
                      lineHeight: '1.3',
                    }}>
                      {ws.name}
                    </h3>

                    {/* Criteria Snippet */}
                    {ws.abstract_acceptance_criteria && (
                      <div style={{ marginBottom: '1.25rem' }}>
                        <span style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: '700', color: '#64748b', marginBottom: '0.25rem' }}>
                          Inclusion Criteria
                        </span>
                        <p style={{
                          fontSize: '0.85rem',
                          color: '#cbd5e1',
                          margin: 0,
                          lineHeight: '1.4',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}>
                          {ws.abstract_acceptance_criteria}
                        </p>
                      </div>
                    )}

                    {/* Metadata Chips */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1.5rem' }}>
                      <span style={{
                        fontSize: '0.75rem',
                        backgroundColor: '#0f172a',
                        border: '1px solid #1e293b',
                        color: '#94a3b8',
                        padding: '0.25rem 0.5rem',
                        borderRadius: '6px',
                      }}>
                        📡 {ws.scrapers?.length || 0} Scrapers
                      </span>
                      <span style={{
                        fontSize: '0.75rem',
                        backgroundColor: '#0f172a',
                        border: '1px solid #1e293b',
                        color: '#94a3b8',
                        padding: '0.25rem 0.5rem',
                        borderRadius: '6px',
                      }}>
                        🎯 {ws.extraction_definitions?.length || 0} Targets
                      </span>
                      <span style={{
                        fontSize: '0.75rem',
                        backgroundColor: '#0f172a',
                        border: '1px solid #1e293b',
                        color: '#94a3b8',
                        padding: '0.25rem 0.5rem',
                        borderRadius: '6px',
                      }}>
                        📄 {ws.ocr_provider ? ws.ocr_provider.toUpperCase() : 'Multimodal Direct'}
                      </span>
                    </div>
                  </div>

                  {/* Card Footer */}
                  <div style={{
                    borderTop: '1px solid #1e293b',
                    paddingTop: '1rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}>
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                      Created {new Date(ws.created_at).toLocaleDateString()}
                    </span>

                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      color: '#38bdf8',
                      fontSize: '0.85rem',
                      fontWeight: '600',
                    }}>
                      <span>SLR Active</span>
                      <CheckCircle size={14} color="#10b981" />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
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
