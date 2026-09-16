import type { WorkspaceSummary } from '@/lib/bff/workspaces/schema'
import { describe, expect, test } from 'bun:test'
import { rerunWorkspaces, runnableWorkspaces, stoppableWorkspaces } from './stoppable'

const ws = (id: string, user_role: string | null) => ({ id, user_role }) as WorkspaceSummary

describe('stoppableWorkspaces, runnableWorkspaces, and rerunWorkspaces', () => {
  test('admins and managers may stop and run; researchers and unknown roles may not', () => {
    const state = {
      kind: 'ok' as const,
      all: [ws('a', 'admin'), ws('m', 'manager'), ws('r', 'researcher'), ws('u', null)],
    }
    expect([...stoppableWorkspaces(state)].sort()).toEqual(['a', 'm'])
    expect([...runnableWorkspaces(state)].sort()).toEqual(['a', 'm'])
  })

  test('only admins may rerun; managers, researchers, and unknown roles may not', () => {
    const state = {
      kind: 'ok' as const,
      all: [ws('a', 'admin'), ws('m', 'manager'), ws('r', 'researcher'), ws('u', null)],
    }
    expect([...rerunWorkspaces(state)].sort()).toEqual(['a'])
  })

  test('no workspaces, or an outage, offers nothing', () => {
    expect(stoppableWorkspaces({ kind: 'none' }).size).toBe(0)
    expect(stoppableWorkspaces({ kind: 'unavailable' }).size).toBe(0)
    expect(runnableWorkspaces({ kind: 'none' }).size).toBe(0)
    expect(runnableWorkspaces({ kind: 'unavailable' }).size).toBe(0)
    expect(rerunWorkspaces({ kind: 'none' }).size).toBe(0)
    expect(rerunWorkspaces({ kind: 'unavailable' }).size).toBe(0)
  })
})
