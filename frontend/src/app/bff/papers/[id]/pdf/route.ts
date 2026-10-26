import { apiFetch } from '@/lib/api/server'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'

export const dynamic = 'force-dynamic'

export const GET = bff('papers', async (_request, ctx) => {
  const { id } = await ctx.params
  const res = await apiFetch(`/api/papers/${id}/pdf/`, {
    headers: { Accept: 'application/pdf, */*' },
  })

  if (res.status === 404) {
    throw problem('not-found', { detail: 'PDF binary not available for this paper.' })
  }

  if (!res.ok) {
    throw problem('upstream-unavailable', { detail: `Backend returned ${res.status} for PDF.` })
  }

  const contentType = res.headers.get('content-type') || 'application/pdf'
  const headers = new Headers({
    'Content-Type': contentType,
    'Cache-Control': 'public, max-age=3600',
  })

  const contentDisposition = res.headers.get('content-disposition')
  if (contentDisposition) {
    headers.set('Content-Disposition', contentDisposition)
  }

  return new Response(res.body, {
    status: 200,
    headers,
  })
})
