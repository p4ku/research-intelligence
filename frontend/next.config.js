/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  // Force unique build ID per build so static bundles are unique and never stale
  generateBuildId: async () => {
    return process.env.NEXT_PUBLIC_BUILD_ID || `build-${Date.now()}`;
  },

  // Headers to prevent browser / proxy from serving stale HTML
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=0, must-revalidate',
          },
          {
            key: 'X-Build-ID',
            value: process.env.NEXT_PUBLIC_BUILD_ID || 'latest',
          },
        ],
      },
      {
        source: '/_next/static/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
