import type { WorkspaceSummary } from '@/lib/bff/workspaces/schema'
import { describe, expect, test } from 'bun:test'
import { stoppableWorkspaces } from './stoppable'

const ws = (id: string, user_role: string | null) => ({ id, user_role }) as WorkspaceSummary

describe('stoppableWorkspaces', () => {
  test('admins and managers may stop; researchers and unknown roles may not', () => {
    const set = stoppableWorkspaces({
      kind: 'ok',
      all: [ws('a', 'admin'), ws('m', 'manager'), ws('r', 'researcher'), ws('u', null)],
    })
    expect([...set].sort()).toEqual(['a', 'm'])
  })

  test('no workspaces, or an outage, offers nothing', () => {
    expect(stoppableWorkspaces({ kind: 'none' }).size).toBe(0)
    expect(stoppableWorkspaces({ kind: 'unavailable' }).size).toBe(0)
  })
})
