/**
 * Settings service. Profile + password ride today's Django endpoints
 * (always real). Preferences are `stub` until the backend adds a per-user
 * digest preference (see the folder README). Server-only.
 */
import 'server-only'

import { django } from '../core/http'
import { sourceOf } from '../core/source'
import { preferences, type PasswordChange, type Preferences, type Profile, type ProfileUpdate } from './schema'
import { passwordChangeResponseDTO, userProfileDTO } from './upstream'

/** Ephemeral per-process store for the stubbed preference (dev only). */
const stubPreferences = new Map<string, Preferences>()

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
      return django(`/api/workspaces/${workspaceId}/preferences/`, preferences)
    }
    return stubPreferences.get(workspaceId) ?? { digest_email: true }
  },

  async setPreferences(workspaceId: string, next: Preferences): Promise<Preferences> {
    if (sourceOf('preferences') === 'django') {
      return django(`/api/workspaces/${workspaceId}/preferences/`, preferences, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(next),
      })
    }
    stubPreferences.set(workspaceId, next)
    return next
  },
}
