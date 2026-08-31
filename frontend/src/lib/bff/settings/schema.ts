/**
 * OUR settings contract: the profile (Django's shape, kept as-is — it is
 * already sane), profile/password updates, and the per-user digest
 * preference we are asking the backend to add. Pure.
 */
import * as z from 'zod'

export const profile = z
  .object({
    id: z.number().int(),
    username: z.string(),
    email: z.string(),
    first_name: z.string(),
    last_name: z.string(),
    full_name: z.string(),
    is_superuser: z.boolean(),
    is_staff: z.boolean(),
    /** Membership count; null for superusers (they see everything). */
    workspaces_count: z.number().int().nullable(),
  })
  .meta({ id: 'Profile' })
export type Profile = z.infer<typeof profile>

export const profileUpdate = z
  .object({
    username: z.string().min(3).max(150).optional(),
    email: z.email().optional(),
    first_name: z.string().max(150).optional(),
    last_name: z.string().max(150).optional(),
  })
  .meta({ id: 'ProfileUpdate' })
export type ProfileUpdate = z.infer<typeof profileUpdate>

export const passwordChange = z
  .object({
    old_password: z.string().min(1),
    new_password: z.string().min(8),
    confirm_password: z.string().min(1),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: 'New passwords do not match.',
    path: ['confirm_password'],
  })
  .meta({ id: 'PasswordChange' })
export type PasswordChange = z.infer<typeof passwordChange>

/** The calling user's notification preference within one workspace. */
export const preferences = z
  .object({ digest_email: z.boolean() })
  .meta({ id: 'WorkspacePreferences' })
export type Preferences = z.infer<typeof preferences>

export const preferencesQuery = z.object({ workspace_id: z.uuid() })
