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
        <h2 style={{ fontSize: '1.5rem', color: '#f1f5f9' }}>MCP Server & Backend Status</h2>
        <p style={{ color: '#cbd5e1' }}>
          MCP Server is active on port <code>8001</code> with SSE transport.
        </p>
      </div>
    </main>
  )
}
