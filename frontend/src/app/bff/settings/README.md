# settings

## Purpose

The Settings page: profile edits, password change, the workspace card
(read-only), and the daily-digest toggle.

## BFF routes

| Route                                             | Backing                                    | Notes                                                                                                                                              |
| ------------------------------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /bff/settings/profile`                       | **real** `GET /api/auth/me/`               | `Profile`                                                                                                                                          |
| `PATCH /bff/settings/profile`                     | **real** `PATCH /api/auth/me/`             | `{username?, email?, first_name?, last_name?}`; uniqueness errors come back as `problem.errors`; the handler re-sets the `sri_user` display cookie |
| `POST /bff/settings/password`                     | **real** `POST /api/auth/change-password/` | `{old_password, new_password, confirm_password}`; Django's field messages surface per field                                                        |
| `GET/PUT /bff/settings/preferences?workspace_id=` | **stub**                                   | `{digest_email: boolean}`; per-process memory until the backend persists it                                                                        |

The workspace card reads the workspaces resource (scrapers, definitions,
digest cron, screening model) — nothing extra needed here.

## Django endpoint we want

`GET/PUT /api/workspaces/{workspace_id}/preferences/` →
`{"digest_email": true}` — the **calling user's** digest preference in that
workspace. Suggested mapping: a Subscriber row keyed to the user's email with
`is_active` as the flag (today subscribers exist but are not REST-writable and
carry no user link). P2.

Worth noting while you're in there (see `docs/backend-handoff.md`): password
change does not invalidate existing JWTs, and `AUTH_PASSWORD_VALIDATORS` are
not applied on the change endpoint (only the serializer's `min_length=8`).

## Flip the flag

`BFF_SOURCE_PREFERENCES=django` once the endpoint exists; the "saved for this
session only" note under the toggle disappears.

## curl

```bash
curl -s -X PATCH localhost:3000/bff/settings/profile -b "sri_access=…" \
  -H 'content-type: application/json' -d '{"first_name":"Josh"}'
curl -s -X PUT "localhost:3000/bff/settings/preferences?workspace_id=$WS" \
  -b "sri_access=…" -H 'content-type: application/json' -d '{"digest_email":false}'
```

## Done criteria

`contract:check` PASS for `settings.preferences.desired`; flag default
flipped; the stub store deleted from `src/lib/bff/settings/service.ts`.
