/** Settings contract registry entries. Pure. */
import type { Operation } from '../core/contract-types'
import { passwordChange, preferences, profile, profileUpdate } from './schema'
import { userProfileDTO } from './upstream'

export const settingsOperations: Operation[] = [
  {
    id: 'settings.profile.current',
    resource: 'preferences',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/auth/me/',
    summary: 'The signed-in profile (PATCH accepts username/email/first_name/last_name).',
    responses: { 200: userProfileDTO },
  },
  {
    id: 'settings.preferences.desired',
    resource: 'preferences',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/workspaces/{workspace_id}/preferences/',
    summary:
      "The calling user's notification preference in this workspace (PUT to change). Backend mapping suggestion: a per-user Subscriber row / is_active.",
    responses: { 200: preferences },
    probe: { requires: ['workspace_id'] },
  },
  {
    id: 'settings.profile.bff',
    resource: 'preferences',
    face: 'bff',
    kind: 'bff',
    method: 'PATCH',
    path: '/bff/settings/profile',
    summary: 'Update the profile; refreshes the display cookie.',
    body: profileUpdate,
    responses: { 200: profile },
  },
  {
    id: 'settings.password.bff',
    resource: 'preferences',
    face: 'bff',
    kind: 'bff',
    method: 'POST',
    path: '/bff/settings/password',
    summary: 'Change the password (field errors come back as problem.errors).',
    body: passwordChange,
    responses: { 200: profile },
  },
  {
    id: 'settings.preferences.bff',
    resource: 'preferences',
    face: 'bff',
    kind: 'bff',
    method: 'PUT',
    path: '/bff/settings/preferences',
    summary: 'The digest-email toggle (?workspace_id=). Stub until Django persists it.',
    body: preferences,
    responses: { 200: preferences },
  },
]
