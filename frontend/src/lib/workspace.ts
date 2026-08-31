/** Cookie that remembers which workspace the user is looking at. */
export const WORKSPACE_COOKIE = 'rs-workspace'

/** Client-side: remember the workspace for a year. Server components re-read it on refresh. */
export function rememberWorkspace(id: string) {
  document.cookie = `${WORKSPACE_COOKIE}=${id};path=/;max-age=31536000;samesite=lax`
}
