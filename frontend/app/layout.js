export const metadata = {
  title: 'Schwarz Research Intelligence',
  description: 'AI-Powered Research & Intelligence Platform',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, -apple-system, sans-serif', backgroundColor: '#0f172a', color: '#f8fafc' }}>
        {children}
      </body>
    </html>
  )
}
