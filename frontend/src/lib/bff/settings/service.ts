/**
 * Settings service. Profile + password ride today's Django endpoints
 * (always real). Preferences are `stub` until the backend adds a per-user
 * digest preference (see the folder README) — the stub does not persist,
 * because there is no per-user store here to persist into. Server-only.
 */
import 'server-only'

import { django } from '../core/http'
import { problem } from '../core/problem'
import { assertUuid } from '../core/validate'
import { sourceOf } from '../core/source'
import { preferences, type PasswordChange, type Preferences, type Profile, type ProfileUpdate } from './schema'
import { passwordChangeResponseDTO, userProfileDTO } from './upstream'

function toProfile(dto: import('zod').infer<typeof userProfileDTO>): Profile {
  return {
    id: dto.id,
    username: dto.username,
    email: dto.email,
    first_name: dto.first_name,
    last_name: dto.last_name,
    full_name: dto.full_name,
    is_superuser: dto.is_superuser,
    is_staff: dto.is_staff,
    workspaces_count: dto.workspaces_count ?? null,
  }
}

export const settings = {
  async profile(): Promise<Profile> {
    return toProfile(await django('/api/auth/me/', userProfileDTO))
  },

  async updateProfile(update: ProfileUpdate): Promise<Profile> {
    const dto = await django('/api/auth/me/', userProfileDTO, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(update),
    })
    return toProfile(dto)
  },

  async changePassword(change: PasswordChange): Promise<string> {
    const res = await django('/api/auth/change-password/', passwordChangeResponseDTO, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(change),
    })
    return res.message
  },

  async getPreferences(workspaceId: string): Promise<Preferences> {
    if (sourceOf('preferences') === 'django') {
      return django(`/api/workspaces/${assertUuid(workspaceId, 'workspace_id')}/preferences/`, preferences)
    }
    // Nothing to read until the endpoint exists. The UI holds the toggle in
    // browser state and says so, rather than us inventing shared server state.
    return { digest_email: true }
  },

  async setPreferences(workspaceId: string, next: Preferences): Promise<Preferences> {
    if (sourceOf('preferences') === 'django') {
      return django(`/api/workspaces/${assertUuid(workspaceId, 'workspace_id')}/preferences/`, preferences, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(next),
      })
    }
    throw problem('not-implemented', {
      detail: 'Digest preferences currently apply to this session only.',
    })
  },
}
