/**
 * The field's keyboard, as a pure reducer so the table below is testable.
 *
 * "Open" is panel visibility, not field focus: the caller passes whether the
 * panel is actually on screen, so a focused field showing nothing is "closed".
 *
 * | key       | closed                     | open, nothing highlighted | open, row i highlighted |
 * | --------- | -------------------------- | ------------------------- | ----------------------- |
 * | ArrowDown | open, highlight the first  | highlight the first       | next row (no wrap)      |
 * | ArrowUp   | —                          | —                         | previous row, then none |
 * | Enter     | submit                     | submit                    | activate row i          |
 * | Escape    | clear the text (if any)    | close, keep the text      | close, keep the text    |
 * | Tab       | —                          | close                     | close                   |
 *
 * "Submit" is Enter with nothing highlighted: Papers with the query.
 */
export interface KeyState {
  open: boolean
  /** -1 = nothing highlighted. */
  cursor: number
  hasText: boolean
}

export type KeyAction =
  | { type: 'open' }
  | { type: 'close' }
  | { type: 'clear' }
  | { type: 'cursor'; cursor: number }
  | { type: 'activate' }
  | { type: 'submit' }
  | { type: 'none' }

export function reduceKey(key: string, state: KeyState, rowCount: number): KeyAction {
  const { open, cursor, hasText } = state
  switch (key) {
    case 'ArrowDown':
      if (rowCount === 0) return open ? { type: 'none' } : { type: 'open' }
      if (!open || cursor < 0) return { type: 'cursor', cursor: 0 }
      return { type: 'cursor', cursor: Math.min(cursor + 1, rowCount - 1) }
    case 'ArrowUp':
      if (!open || cursor < 0) return { type: 'none' }
      return { type: 'cursor', cursor: cursor - 1 }
    case 'Enter':
      return open && cursor >= 0 && cursor < rowCount ? { type: 'activate' } : { type: 'submit' }
    case 'Escape':
      if (open) return { type: 'close' }
      return hasText ? { type: 'clear' } : { type: 'none' }
    case 'Tab':
      return open ? { type: 'close' } : { type: 'none' }
    default:
      return { type: 'none' }
  }
}

/** Keys whose browser default the field overrides (Escape natively empties a search input). */
export const HANDLED_KEYS = new Set(['ArrowDown', 'ArrowUp', 'Enter', 'Escape'])
