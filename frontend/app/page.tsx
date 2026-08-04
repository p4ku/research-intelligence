"use client";

import React from 'react';

export default function HomePage() {
  return (
    <main style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '2.5rem', fontWeight: 'bold', color: '#38bdf8' }}>
        Schwarz Research Intelligence
      </h1>
      <p style={{ fontSize: '1.2rem', color: '#94a3b8' }}>
        Multi-Agent Systematic Literature Review & Intelligence Platform
      </p>
      <div style={{ marginTop: '2rem', padding: '1.5rem', borderRadius: '8px', backgroundColor: '#1e293b', border: '1px solid #334155' }}>
        <h2 style={{ fontSize: '1.5rem', color: '#f1f5f9', margin: '0 0 1rem 0' }}>Services & System Status</h2>
        <p style={{ color: '#cbd5e1', margin: '0 0 1.5rem 0', lineHeight: '1.6' }}>
          Verify the real-time operational status, latencies, and HTTP response endpoints of the Django REST API and the FastMCP integration layer.
        </p>
        <a 
          href="/status" 
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            backgroundColor: '#0284c7',
            color: '#ffffff',
            textDecoration: 'none',
            padding: '0.625rem 1.25rem',
            borderRadius: '6px',
            fontWeight: '600',
            fontSize: '0.95rem',
            transition: 'background-color 0.2s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#0369a1'; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '#0284c7'; }}
        >
          Check System Status
        </a>
      </div>
    </main>
  );
}
