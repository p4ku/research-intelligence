"use client";

import React from 'react';
import { useAuth } from '../lib/auth/auth-context';
import { 
  Activity, 
  Layers, 
  LogOut, 
  User, 
  ShieldCheck, 
  Sparkles,
  Lock
} from 'lucide-react';

export default function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <nav style={{
      backgroundColor: 'rgba(15, 23, 42, 0.85)',
      backdropFilter: 'blur(12px)',
      borderBottom: '1px solid #1e293b',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      padding: '0.75rem 1.5rem',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
    }}>
      {/* Brand & Main Links */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
        <a href="/" style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          textDecoration: 'none',
          color: '#f8fafc',
        }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(56, 189, 248, 0.25)',
          }}>
            <Sparkles size={18} color="#ffffff" />
          </div>
          <div>
            <div style={{ fontWeight: '800', fontSize: '1.05rem', letterSpacing: '-0.02em', lineHeight: '1.2' }}>
              Schwarz Research Intelligence
            </div>
            <div style={{ fontSize: '0.7rem', color: '#94a3b8', fontWeight: '500' }}>
              SLR & Deep-Tech Scouting
            </div>
          </div>
        </a>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <a
            href="/"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              color: '#cbd5e1',
              textDecoration: 'none',
              fontSize: '0.875rem',
              fontWeight: '500',
              padding: '0.375rem 0.75rem',
              borderRadius: '6px',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = '#38bdf8';
              e.currentTarget.style.backgroundColor = 'rgba(56,189,248,0.08)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = '#cbd5e1';
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <Layers size={15} />
            Workspaces
          </a>

          <a
            href="/status"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              color: '#cbd5e1',
              textDecoration: 'none',
              fontSize: '0.875rem',
              fontWeight: '500',
              padding: '0.375rem 0.75rem',
              borderRadius: '6px',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = '#38bdf8';
              e.currentTarget.style.backgroundColor = 'rgba(56,189,248,0.08)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = '#cbd5e1';
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <Activity size={15} />
            System Status
          </a>
        </div>
      </div>

      {/* User Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        {isAuthenticated && user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            {/* User Pill */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              backgroundColor: '#0f172a',
              border: '1px solid #1e293b',
              padding: '0.35rem 0.75rem',
              borderRadius: '9999px',
            }}>
              <div style={{
                width: '28px',
                height: '28px',
                borderRadius: '50%',
                backgroundColor: '#0284c7',
                color: '#ffffff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.75rem',
                fontWeight: '700',
              }}>
                {user.first_name ? user.first_name[0] : user.username[0].toUpperCase()}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: '600', color: '#f8fafc', lineHeight: '1.2' }}>
                  {user.full_name || user.username}
                </span>
                <span style={{ fontSize: '0.7rem', color: '#64748b' }}>
                  {user.is_superuser ? 'Superuser' : (user.email || 'Researcher')}
                </span>
              </div>
            </div>

            {/* Logout Button */}
            <button
              onClick={logout}
              title="Sign Out"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.375rem',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                color: '#f87171',
                padding: '0.4rem 0.75rem',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: '600',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.2)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
              }}
            >
              <LogOut size={14} />
              Logout
            </button>
          </div>
        ) : (
          <a
            href="/login"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: '#0284c7',
              color: '#ffffff',
              padding: '0.45rem 1rem',
              borderRadius: '8px',
              textDecoration: 'none',
              fontSize: '0.85rem',
              fontWeight: '600',
              boxShadow: '0 2px 8px rgba(2,132,199,0.3)',
              transition: 'background-color 0.2s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#0369a1'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#0284c7'; }}
          >
            <Lock size={14} />
            Sign In
          </a>
        )}
      </div>
    </nav>
  );
}
