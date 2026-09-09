/**
 * Which domains the UI is allowed to name. Calibration workspaces are a
 * backend working set — they exist so scoring can be tuned against a known
 * corpus, and analysts should never see them in a domain list, a briefing or
 * the papers table. The data carries both spellings ("calibration" and the
 * misspelt "callibration"), so match either. Pure.
 */

/** Anything whose name contains calibration, however it is spelt or cased. */
const CALIBRATION = /call?ibration/i

/** True when this domain is backend scaffolding rather than an analyst's. */
export function isHiddenWorkspace(name: string): boolean {
  return CALIBRATION.test(name)
}
