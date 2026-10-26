// ==============================================================================
// 🧠 System Branding & Platform Configuration
// Reads environment variables with clean fallback defaults.
// Configurable via Docker Compose (NEXT_PUBLIC_APP_NAME / APP_NAME).
// ==============================================================================

export const APP_NAME =
  process.env.NEXT_PUBLIC_APP_NAME || process.env.APP_NAME || 'Research Intelligence'

export const APP_SHORT_NAME =
  process.env.NEXT_PUBLIC_APP_SHORT_NAME || process.env.APP_SHORT_NAME || 'SRI'

export const APP_DESCRIPTION =
  process.env.NEXT_PUBLIC_APP_DESCRIPTION ||
  process.env.APP_DESCRIPTION ||
  `${APP_NAME} reads new papers as they land, scores them across the dimensions that matter, and surfaces what deserves attention.`
