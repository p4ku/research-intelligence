/**
 * zod transcription of Django's auth/profile surface as it exists today
 * (`backend/api/serializers/auth.py`, `api/views/auth.py`). Pure.
 */
import * as z from 'zod'

/** UserProfileSerializer; /api/auth/me/ GET adds workspaces_count (null for superusers). */
export const userProfileDTO = z.looseObject({
  id: z.number(),
  username: z.string(),
  email: z.string(),
  first_name: z.string(),
  last_name: z.string(),
  /** "first last" or the username when empty. */
  full_name: z.string(),
  is_superuser: z.boolean(),
  is_staff: z.boolean(),
  workspaces_count: z.number().nullable().optional(),
})

export const passwordChangeResponseDTO = z.looseObject({ message: z.string() })
