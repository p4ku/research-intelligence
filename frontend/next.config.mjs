import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Self-contained server bundle for the Docker image (node server.js).
  output: 'standalone',
  // Django's URLs end in a slash; Next's default redirect of /api/papers/ →
  // /api/papers would fire before the proxy could forward it. The proxy
  // normalises trailing slashes for the app's own routes instead.
  skipTrailingSlashRedirect: true,
  // CI passes the git sha so every image has a stable, identifiable build id.
  generateBuildId: async () => process.env.BUILD_ID ?? null,
  // Parallel agents build into their own directories (see build-management).
  distDir: process.env.BUILD_DIR || '.next',
  turbopack: {
    root: resolve(__dirname),
  },
  devIndicators: false,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ]
  },
}

export default nextConfig
