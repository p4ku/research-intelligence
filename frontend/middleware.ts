import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // Backend paths that must never be rendered as frontend SPA 404 pages
  const isBackendRoute =
    pathname.startsWith('/admin') ||
    pathname.startsWith('/api') ||
    pathname.startsWith('/mcp') ||
    pathname.startsWith('/docs') ||
    pathname.startsWith('/swagger') ||
    pathname.startsWith('/redoc') ||
    pathname.startsWith('/schema') ||
    pathname.startsWith('/static') ||
    pathname.startsWith('/media') ||
    pathname.startsWith('/health') ||
    pathname.startsWith('/sse') ||
    pathname.startsWith('/messages');

  if (isBackendRoute) {
    // If running in development or if Cloud Foundry Gorouter forwarded backend request to frontend container,
    // proxy the request to the Django API / FastMCP server
    const targetBase =
      process.env.BACKEND_INTERNAL_URL ||
      process.env.NEXT_PUBLIC_API_URL?.replace('/api', '') ||
      'http://localhost:8000';

    const cleanTargetBase = targetBase.endsWith('/') ? targetBase.slice(0, -1) : targetBase;
    const targetUrl = `${cleanTargetBase}${pathname}${search}`;

    return NextResponse.rewrite(new URL(targetUrl));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/admin/:path*',
    '/api/:path*',
    '/mcp/:path*',
    '/docs/:path*',
    '/swagger/:path*',
    '/redoc/:path*',
    '/schema/:path*',
    '/static/:path*',
    '/media/:path*',
    '/health/:path*',
    '/sse',
    '/messages',
  ],
};
