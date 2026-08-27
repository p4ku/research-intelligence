"use client";

import React, { useState, useEffect } from 'react';
import { useAuth } from '../../lib/auth/auth-context';
import { 
  Lock, 
  Mail, 
  Eye, 
  EyeOff, 
  Sparkles, 
  ShieldAlert, 
  ArrowRight,
  ShieldCheck,
  Activity,
  ArrowLeft
} from 'lucide-react';

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      window.location.href = '/';
    }
  }, [isLoading, isAuthenticated]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier || !password) {
      setError('Please enter both your email/username and password.');
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      await login(identifier, password);
      window.location.href = '/';
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
      backgroundImage: 'radial-gradient(circle at 50% 20%, #1e1b4b 0%, #090d16 65%)',
      color: '#f8fafc',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '3rem 1rem',
    }}>
      <div style={{ maxWidth: '440px', width: '100%' }}>
        
        {/* Back Link */}
        <div style={{ marginBottom: '1.5rem' }}>
          <a
            href="/"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              color: '#94a3b8',
              textDecoration: 'none',
              fontSize: '0.875rem',
              transition: 'color 0.2s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#f8fafc'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; }}
          >
            <ArrowLeft size={16} />
            Back to Home
          </a>
        </div>

        {/* Header Branding */}
        <div style={{ textAlign: 'center', marginBottom: '2.25rem' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '56px',
            height: '56px',
            borderRadius: '16px',
            background: 'linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)',
            boxShadow: '0 8px 24px rgba(56, 189, 248, 0.25)',
            marginBottom: '1.25rem',
          }}>
            <Sparkles size={28} color="#ffffff" />
          </div>
          <h1 style={{
            fontSize: '1.85rem',
            fontWeight: '800',
            letterSpacing: '-0.025em',
            margin: '0 0 0.5rem 0',
            background: 'linear-gradient(to right, #f8fafc, #94a3b8)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}>
            Sign In to Workspaces
          </h1>
          <p style={{ color: '#94a3b8', fontSize: '0.95rem', margin: 0 }}>
            Enter your credentials to access assigned SLR projects
          </p>
        </div>

        {/* Login Card */}
        <div style={{
          backgroundColor: '#111827',
          border: '1px solid #1f2937',
          borderRadius: '16px',
          padding: '2.25rem',
          boxShadow: '0 20px 40px -15px rgba(0, 0, 0, 0.5)',
        }}>
          {error && (
            <div style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              borderRadius: '8px',
              padding: '0.875rem 1rem',
              color: '#f87171',
              fontSize: '0.875rem',
              marginBottom: '1.5rem',
              lineHeight: '1.4',
            }}>
              <ShieldAlert size={18} style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>{error}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Email / Username Field */}
            <div>
              <label style={{
                display: 'block',
                fontSize: '0.85rem',
                fontWeight: '600',
                color: '#cbd5e1',
                marginBottom: '0.5rem',
              }}>
                Email or Username
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="admin or researcher@schwarz.de"
                  autoComplete="username"
                  required
                  style={{
                    width: '100%',
                    backgroundColor: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    padding: '0.75rem 1rem 0.75rem 2.5rem',
                    color: '#f8fafc',
                    fontSize: '0.95rem',
                    outline: 'none',
                    boxSizing: 'border-box',
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = '#38bdf8'; }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = '#334155'; }}
                />
                <Mail size={16} color="#64748b" style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                }} />
              </div>
            </div>

            {/* Password Field */}
            <div>
              <label style={{
                display: 'block',
                fontSize: '0.85rem',
                fontWeight: '600',
                color: '#cbd5e1',
                marginBottom: '0.5rem',
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
                    padding: '0.75rem 2.5rem 0.75rem 2.5rem',
                    color: '#f8fafc',
                    fontSize: '0.95rem',
                    outline: 'none',
                    boxSizing: 'border-box',
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = '#38bdf8'; }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = '#334155'; }}
                />
                <Lock size={16} color="#64748b" style={{
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
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Submit Button */}
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
                padding: '0.85rem',
                fontSize: '1rem',
                fontWeight: '700',
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                boxShadow: '0 4px 14px rgba(2, 132, 199, 0.4)',
                transition: 'background-color 0.2s',
              }}
              onMouseEnter={(e) => {
                if (!isSubmitting) e.currentTarget.style.backgroundColor = '#0369a1';
              }}
              onMouseLeave={(e) => {
                if (!isSubmitting) e.currentTarget.style.backgroundColor = '#0284c7';
              }}
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

          {/* Footer note */}
          <div style={{
            marginTop: '1.75rem',
            paddingTop: '1.25rem',
            borderTop: '1px solid #1f2937',
            fontSize: '0.8rem',
            color: '#64748b',
            textAlign: 'center',
            lineHeight: '1.5',
          }}>
            <div>Secure JWT token session with automatic renewal.</div>
          </div>
        </div>
      </div>
    </div>
  );
}
