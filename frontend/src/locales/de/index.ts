// Merged German dictionary, keyed by the exact English source string.
// One module per app area; regenerate the imports when adding an area.
// Later spreads win on duplicate keys; the consistency audit keeps duplicates identical.
// Chrome only: content from the backend (titles, abstracts, briefs, answers,
// screening reasons, dimension names) is never translated.
import { dict as ask } from './ask'
import { dict as briefing } from './briefing'
import { dict as chrome } from './chrome'
import { dict as components } from './components'
import { dict as dashboard } from './dashboard'
import { dict as errors } from './errors'
import { dict as login } from './login'
import { dict as papers } from './papers'
import { dict as runs } from './runs'
import { dict as settings } from './settings'
import { dict as tuning } from './tuning'

export const de: Record<string, string> = {
  ...ask,
  ...briefing,
  ...chrome,
  ...components,
  ...dashboard,
  ...errors,
  ...login,
  ...papers,
  ...runs,
  ...settings,
  ...tuning,
}
