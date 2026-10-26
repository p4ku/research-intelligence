import { describe, expect, mock, test } from 'bun:test'
import { NextRequest } from 'next/server'

mock.module('server-only', () => ({}))

const mockCohortId = 'c0a80123-0000-4000-8000-000000000001'
const mockPaperId = 'd0a80123-0000-4000-8000-000000000001'
const mockRunId = 'f0a80123-0000-4000-8000-000000000001'

describe('BFF Audit Route Handlers (Stub mode)', () => {
  test('GET /bff/audit/queue returns queue array', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { GET: getQueue } = await import('./queue/route')
    const req = new NextRequest('http://localhost:3000/bff/audit/queue')
    const res = await getQueue(req, { params: Promise.resolve({}) })
    expect(res.status).toBe(200)

    const data = await res.json()
    expect(Array.isArray(data)).toBe(true)
    expect(data.length).toBeGreaterThan(0)
    expect(data[0].cohort_id).toBe(mockCohortId)
  })

  test('GET /bff/audit/cohorts/[cohortId] returns cohort detail', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { GET: getCohort } = await import('./cohorts/[cohortId]/route')
    const req = new NextRequest(`http://localhost:3000/bff/audit/cohorts/${mockCohortId}`)
    const res = await getCohort(req, {
      params: Promise.resolve({ cohortId: mockCohortId }),
    })
    expect(res.status).toBe(200)

    const data = await res.json()
    expect(data.cohort_id).toBe(mockCohortId)
    expect(data.total_papers).toBe(10)
  })

  test('GET /bff/audit/cohorts/[cohortId]/papers/[paperId] returns paper detail', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { GET: getPaper } = await import('./cohorts/[cohortId]/papers/[paperId]/route')
    const req = new NextRequest(
      `http://localhost:3000/bff/audit/cohorts/${mockCohortId}/papers/${mockPaperId}`,
    )
    const res = await getPaper(req, {
      params: Promise.resolve({ cohortId: mockCohortId, paperId: mockPaperId }),
    })
    expect(res.status).toBe(200)

    const data = await res.json()
    expect(data.paper_id).toBe(mockPaperId)
    expect(data.cohort_id).toBe(mockCohortId)
    expect(data.ai_decision).toBe('include')
  })

  test('POST /bff/audit/cohorts/[cohortId]/papers/[paperId]/submit processes review decision', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { POST: submitReview } =
      await import('./cohorts/[cohortId]/papers/[paperId]/submit/route')
    const req = new NextRequest(
      `http://localhost:3000/bff/audit/cohorts/${mockCohortId}/papers/${mockPaperId}/submit`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'agree' }),
      },
    )
    const res = await submitReview(req, {
      params: Promise.resolve({ cohortId: mockCohortId, paperId: mockPaperId }),
    })
    expect(res.status).toBe(200)

    const data = await res.json()
    expect(data.status).toBe('reviewed')
    expect(data.decision).toBe('include')
  })

  test('POST /bff/audit/runs/[runId]/resume confirms run resumption', async () => {
    process.env.BFF_SOURCE_AUDIT = 'stub'
    const { POST: resumeRun } = await import('./runs/[runId]/resume/route')
    const req = new NextRequest(`http://localhost:3000/bff/audit/runs/${mockRunId}/resume`, {
      method: 'POST',
    })
    const res = await resumeRun(req, {
      params: Promise.resolve({ runId: mockRunId }),
    })
    expect(res.status).toBe(200)

    const data = await res.json()
    expect(data.status).toBe('resumed')
    expect(data.pipeline_run_id).toBe(mockRunId)
  })
})
