"use client";

import React from 'react';
import { 
  Sparkles, 
  Globe, 
  Cpu, 
  Database, 
  Lock, 
  ArrowRight, 
  Activity 
} from 'lucide-react';

export default function LandingPage() {
  return (
    <div style={{
      minHeight: 'calc(100vh - 65px)',
      backgroundColor: '#090d16',
      backgroundImage: 'radial-gradient(circle at 50% 15%, #1e1b4b 0%, #090d16 65%)',
      color: '#f8fafc',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: '3.5rem 1.5rem',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
    }}>
      <div style={{ maxWidth: '850px', width: '100%', textAlign: 'center' }}>
        {/* Badge */}
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
          marginBottom: '1.5rem',
        }}>
          <Sparkles size={15} />
          Multi-Agent Systematic Literature Review & Intelligence Platform
        </div>

        {/* Title */}
        <h1 style={{
          fontSize: '3.25rem',
          fontWeight: '800',
          letterSpacing: '-0.03em',
          lineHeight: '1.15',
          margin: '0 0 1.5rem 0',
          background: 'linear-gradient(to right, #f8fafc 30%, #94a3b8 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}>
          Automated Academic Literature Review & Deep-Tech Scouting
        </h1>

        <p style={{
          fontSize: '1.25rem',
          color: '#94a3b8',
          maxWidth: '680px',
          margin: '0 auto 2.75rem auto',
          lineHeight: '1.6',
        }}>
          Ingest papers across ArXiv, OpenAlex, and Lens. Screen full-text PDFs with multimodal Gemini 3.7 Flash and extract validated intelligence matrices.
        </p>

        {/* Action Buttons */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '1.25rem',
          flexWrap: 'wrap',
          marginBottom: '4rem',
        }}>
          <a
            href="/login"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.625rem',
              backgroundColor: '#0284c7',
              color: '#ffffff',
              padding: '0.9rem 2rem',
              borderRadius: '10px',
              textDecoration: 'none',
              fontSize: '1.05rem',
              fontWeight: '700',
              boxShadow: '0 8px 24px rgba(2, 132, 199, 0.4)',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#0369a1';
              e.currentTarget.style.transform = 'translateY(-2px)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#0284c7';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            <Lock size={18} />
            Sign In to Workspaces
            <ArrowRight size={18} />
          </a>

          <a
            href="/status"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              color: '#f1f5f9',
              padding: '0.9rem 1.75rem',
              borderRadius: '10px',
              textDecoration: 'none',
              fontSize: '1.05rem',
              fontWeight: '600',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#334155'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#1e293b'; }}
          >
            <Activity size={18} color="#38bdf8" />
            System Diagnostics
          </a>
        </div>

        {/* Feature Highlights Grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: '1.5rem',
          textAlign: 'left',
        }}>
          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.75rem',
          }}>
            <div style={{ color: '#38bdf8', marginBottom: '0.75rem' }}><Globe size={24} /></div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: '700', margin: '0 0 0.5rem 0', color: '#f8fafc' }}>Multi-Source Ingestion</h3>
            <p style={{ fontSize: '0.875rem', color: '#94a3b8', margin: 0, lineHeight: '1.5' }}>
              Real-time scrapers for ArXiv, OpenAlex, and Lens with title, DOI, and arXiv ID deduplication across millions of papers.
            </p>
          </div>

          <div style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '12px',
            padding: '1.75rem',
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
            padding: '1.75rem',
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
