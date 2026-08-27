"use client";

import React, { useState, useEffect } from 'react';
import { useAuth } from '../lib/auth/auth-context';
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
  UserCheck,
  Lock,
  Mail,
  Eye,
  EyeOff,
  BookOpen,
  Database
} from 'lucide-react';

export default function HomePage() {
  const { user, isAuthenticated, isLoading: isAuthLoading } = useAuth();

  if (isAuthLoading) {
    return (
      <div style={{
        minHeight: '80vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '1.25rem',
        color: '#94a3b8',
      }}>
        <div style={{
          width: '48px',
          height: '48px',
          borderRadius: '12px',
          background: 'linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          animation: 'pulse 1.5s ease-in-out infinite',
        }}>
          <Sparkles size={24} color="#ffffff" />
        </div>
        <div style={{ fontSize: '0.95rem', fontWeight: '500' }}>
          Loading session...
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <UnauthenticatedLandingWithForm />;
  }

  return <DashboardContent />;
}

function UnauthenticatedLandingWithForm() {
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier || !password) {
      setError('Please enter your username/email and password.');
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      await login(identifier, password);
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check your credentials.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{
      minHeight: 'calc(100vh - 65px)',
      backgroundColor: '#090d16',
      backgroundImage: 'radial-gradient(circle at 50% 15%, #1e1b4b 0%, #090d16 65%)',
      color: '#f8fafc',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: '3rem 1.5rem',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
    }}>
      <div style={{ maxWidth: '1100px', width: '100%' }}>
        {/* Main Grid: Hero Info + Direct Sign-In Card */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
          gap: '3rem',
          alignItems: 'center',
          marginBottom: '4rem',
        }}>
          {/* Left: Platform Overview */}
          <div>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              backgroundColor: 'rgba(56, 189, 248, 0.1)',
              border: '1px solid rgba(56, 189, 248, 0.25)',
              borderRadius: '9999px',
              padding: '0.35rem 0.9rem',
              fontSize: '0.85rem',
              fontWeight: '600',
              color: '#38bdf8',
              marginBottom: '1.25rem',
            }}>
              <Sparkles size={15} />
              SLR & Deep-Tech Scouting Intelligence
            </div>

            <h1 style={{
              fontSize: '2.75rem',
              fontWeight: '800',
              letterSpacing: '-0.03em',
              lineHeight: '1.15',
              margin: '0 0 1.25rem 0',
              background: 'linear-gradient(to right, #f8fafc 30%, #94a3b8 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>
              Schwarz Research Intelligence Platform
            </h1>

            <p style={{
              fontSize: '1.1rem',
              color: '#94a3b8',
              lineHeight: '1.6',
              margin: '0 0 2rem 0',
            }}>
              Automate multi-source academic literature ingestion across ArXiv, OpenAlex, and Lens. Screen full-text PDFs with multimodal Gemini 3.7 Flash and extract validated intelligence matrices.
            </p>

            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <a
                href="/status"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  color: '#f1f5f9',
                  padding: '0.75rem 1.25rem',
                  borderRadius: '8px',
                  textDecoration: 'none',
                  fontSize: '0.9rem',
                  fontWeight: '600',
                  transition: 'background-color 0.2s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#334155'; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#1e293b'; }}
              >
                <Activity size={16} color="#38bdf8" />
                Live Infrastructure Status
              </a>
            </div>
          </div>

          {/* Right: Embedded Interactive Sign-In Card */}
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '16px',
            padding: '2.25rem',
            boxShadow: '0 20px 40px -15px rgba(0, 0, 0, 0.5)',
          }}>
            <div style={{ marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <Lock size={20} color="#38bdf8" />
                <h2 style={{ fontSize: '1.4rem', fontWeight: '700', margin: 0, color: '#f8fafc' }}>
                  Sign In to Workspaces
                </h2>
              </div>
              <p style={{ fontSize: '0.875rem', color: '#94a3b8', margin: 0 }}>
                Enter your credentials to access assigned SLR projects
              </p>
            </div>

            {error && (
              <div style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.625rem',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                borderRadius: '8px',
                padding: '0.75rem 1rem',
                color: '#f87171',
                fontSize: '0.85rem',
                marginBottom: '1.25rem',
                lineHeight: '1.4',
              }}>
                <ShieldAlert size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
                <div>{error}</div>
              </div>
            )}

            <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
              <div>
                <label style={{
                  display: 'block',
                  fontSize: '0.8rem',
                  fontWeight: '600',
                  color: '#cbd5e1',
                  marginBottom: '0.4rem',
                }}>
                  Email or Username
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type="text"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="admin or user@schwarz.de"
                    autoComplete="username"
                    required
                    style={{
                      width: '100%',
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '8px',
                      padding: '0.7rem 1rem 0.7rem 2.4rem',
                      color: '#f8fafc',
                      fontSize: '0.9rem',
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = '#38bdf8'; }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = '#334155'; }}
                  />
                  <Mail size={15} color="#64748b" style={{
                    position: 'absolute',
                    left: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                  }} />
                </div>
              </div>

              <div>
                <label style={{
                  display: 'block',
                  fontSize: '0.8rem',
                  fontWeight: '600',
                  color: '#cbd5e1',
                  marginBottom: '0.4rem',
                }}>
                  Password
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    autoComplete="current-password"
                    required
                    style={{
                      width: '100%',
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '8px',
                      padding: '0.7rem 2.4rem 0.7rem 2.4rem',
                      color: '#f8fafc',
                      fontSize: '0.9rem',
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = '#38bdf8'; }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = '#334155'; }}
                  />
                  <Lock size={15} color="#64748b" style={{
                    position: 'absolute',
                    left: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                  }} />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{
                      position: 'absolute',
                      right: '12px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'transparent',
                      border: 'none',
                      color: '#64748b',
                      cursor: 'pointer',
                      padding: 0,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                style={{
                  marginTop: '0.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                  backgroundColor: isSubmitting ? '#0369a1' : '#0284c7',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '0.8rem',
                  fontSize: '0.95rem',
                  fontWeight: '700',
                  cursor: isSubmitting ? 'not-allowed' : 'pointer',
                  boxShadow: '0 4px 14px rgba(2, 132, 199, 0.4)',
                  transition: 'background-color 0.2s',
                }}
                onMouseEnter={(e) => { if (!isSubmitting) e.currentTarget.style.backgroundColor = '#0369a1'; }}
                onMouseLeave={(e) => { if (!isSubmitting) e.currentTarget.style.backgroundColor = '#0284c7'; }}
              >
                {isSubmitting ? (
                  <span>Signing In...</span>
                ) : (
                  <>
                    <span>Sign In</span>
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1.5rem',
          textAlign: 'left',
        }}>
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.5rem',
          }}>
            <div style={{ color: '#38bdf8', marginBottom: '0.75rem' }}><Globe size={24} /></div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: '700', margin: '0 0 0.5rem 0', color: '#f8fafc' }}>Multi-Source Ingestion</h3>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8', margin: 0, lineHeight: '1.5' }}>
              Scrapers for ArXiv, OpenAlex, and Lens with title, DOI, and arXiv ID deduplication across millions of papers.
            </p>
          </div>

          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.5rem',
          }}>
            <div style={{ color: '#a855f7', marginBottom: '0.75rem' }}><Cpu size={24} /></div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: '700', margin: '0 0 0.5rem 0', color: '#f8fafc' }}>Dual-Stage AI Screening</h3>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8', margin: 0, lineHeight: '1.5' }}>
              Stage 1 Abstract Screening & Stage 2 Multimodal PDF evaluation using Google Gemini 3.7 Flash.
            </p>
          </div>

          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.5rem',
          }}>
            <div style={{ color: '#10b981', marginBottom: '0.75rem' }}><Database size={24} /></div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: '700', margin: '0 0 0.5rem 0', color: '#f8fafc' }}>Structured Extractions</h3>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8', margin: 0, lineHeight: '1.5' }}>
              Schema-validated extraction into structured matrices with evidence quotes, confidence, and TRL metrics.
            </p>
          </div>
        </div>
      </div>
    </div>
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
