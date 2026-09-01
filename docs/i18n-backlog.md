# German / English backlog (P1 & P2)

Findings from the DE/EN audit of 2026-09-01 (`main @ e78847e`) that are **not**
part of the immediate pre-handover fixes. The P0 items (html `lang`,
Accept-Language default, English login, English template prose in the German
UI, dev-facing copy, and a set of dictionary corrections) are tracked in their
own PR and are not repeated here.

Scope of the audit: every `t()` call in `frontend/src` vs the merged German
dictionary (`src/locales/de/`), the backend's language handling, and a
DE + EN screenshot pass over all nine screens against the 2026-08-31 prod
snapshot (`bun run screenshots --lang de`).

How to re-run the coverage check: the audit script is committed as a test
(see P1.1); until then, `bun test` + the screenshot script are the tools.

---

## P1 — this sprint

### P1.1 Guard translation coverage in CI
- Keys are the English source strings (gettext-style). Editing English copy
  silently drops the German — `makeT` falls back to English with only a
  dev-time `console.warn` (`src/lib/i18n.ts:19-26`). Nothing fails.
- CI (`.github/workflows/ci.yml`) runs Django tests and a Docker build only —
  no `bun run typecheck / test / lint`.
- Action: commit the audit script as `frontend/src/lib/i18n.test.ts`
  (fail on: keys used in source but missing from the dictionary; the same key
  defined with different values in two modules; `{placeholder}` mismatches
  between key and translation. Warn on: dead keys) and add the frontend
  checks to CI.

### P1.2 One date locale, explicit time zone
- Three English date locales are in use: `formatDate` uses `en-US`
  ("Aug 31, 2026", `src/lib/i18n.ts:38-44`) while the Ask history rail
  (`ask/history-rail.tsx:19`), briefing dates (`briefing/format.ts`) and
  Studio (`studio/runs/page.tsx:48`) use `en-GB` ("31 Aug 2026").
- `formatDate` and `dayLabel` pass no `timeZone`: server-rendered dates use
  the container's zone (UTC on Cloud Foundry), client-rendered ones the
  browser's. `2026-06-03T23:30Z` renders "Jun 3" on the server and
  "4. Juni" in a Berlin browser (verified in Node).
- `briefing/format.ts` and Studio do it right (explicit UTC, Studio labels
  the column "(UTC)").
- Action: one `LOCALES = { en: 'en-GB', de: 'de-DE' }` constant in
  `src/lib/i18n.ts`; pick a display zone (`Europe/Berlin` for the reading
  app; Studio stays UTC-labelled) and pass it everywhere.

### P1.3 Localised number formatting
- Scores render with `toFixed(1)` → "62.0" in the German UI, should be
  "62,0" (`components/scanner-ui.tsx:315`, `components/signal-ledger.tsx:41`).
- Token counts use `toLocaleString()` with no locale → browser-dependent
  (`ask/scanner-turn.tsx:251`).
- `fmt()` interpolates raw numbers — "1234 Papers", never "1.234"
  (`src/lib/i18n.ts:31`).
- Percent needs the German space: "90 %" not "90%" (DIN 5008; narrow
  no-break space) — e.g. `Konfidenz 90%` on the paper detail
  (`papers/[id]/page.tsx:241`).
- Action: `formatNumber(n, lang, opts)` on `Intl.NumberFormat`; a percent
  helper; teach `fmt` to format numeric vars with the active locale.

### P1.4 Plural handling
- `1 paper` / `{n} papers` is special-cased in one place
  (`briefing/edition-browser.tsx:142`) and nowhere else. Live defects:
  "1 Fragen" (`'{n} turns'`, `ask/history-rail.tsx:72`), "0 gefragt"
  (`'{n} asked'`, `ask/ask.tsx:301`), plus `{n} hits`, `{n} tokens`,
  `{n} of {total} claims grounded`.
- Action: a small `plural(n, one, other)` helper on `Intl.PluralRules`
  (German and English both have simple one/other rules), or `one|other`
  key pairs.

### P1.5 Untranslated accessibility strings and tab titles
- Hardcoded `aria-label`s in shared components: "Previous page" /
  "Next page" (`components/pagination.tsx:20,48`), "Open navigation" /
  "Close navigation" (`sidebar-layout.tsx:40,71`, `stacked-layout.tsx:40,68`),
  "Loading" (`ui/spinner.tsx:9`), "Breadcrumb" (`scanner-ui.tsx:16`).
- `/papers` and `/settings` export static `metadata.title` — the browser tab
  says "Settings · Research Intelligence" in German mode — while every other
  page already uses `generateMetadata` + `getT()`.
- The root layout `description` (used for OpenGraph) is English only.

### P1.6 German mobile overflow
- German strings are ~30% longer and widen the layout past the viewport
  (measured with `bun run screenshots --lang de --viewports mobile`):
  `/briefing` +375px, `/settings` +132px (English: +17px — the German labels
  in the workspace definition list are the delta), `/papers` +15px,
  `/papers/[id]` +14px.
- Action: fix alongside the known English overflow items in
  `local-docs/open-items.md`; re-measure in both languages.

### P1.7 Prune dead dictionary entries (91 of 318 keys, 29%)
Left over from the prototype; they inflate the modules, hide real coverage,
and four are ~400-character fixture paragraphs. The P1.1 test derives the
current list mechanically; groups as of the audit:
- Concept-frame chrome (`de/chrome.ts`): Hide core concepts, Hide extra
  concepts, Future Phase Concepts, Phase 3a/3b Concepts, Shared, Trends,
  Tier 1/2 concepts, Watchlist, Designed for:.
- Old dashboard (`de/dashboard.ts`): Here's what the scanner surfaced…,
  Identified, Evaluated, Deep-dived, vs. yesterday, Morning briefing,
  Read the briefing →, Top signals today, Novelty … · Significance …,
  The field, Open radar →, Engage early, Act now, Archive, Monitor,
  Fastest rising, Lead story, funnel arrow strings, Headlines, Headline
  stories, Full analysis →, this run, to teams, 1 lead · {n} more,
  Browse the full corpus →, The run, Focus fields, identified, deep-dived,
  handed off, Signal, Newest, Pages, Showing {from}–{to} of {total},
  {current} / {total}, ← Prev, Next →, Not yet active, and the hardcoded
  "dense day for Hybrid Computing" fixture paragraph.
- Workshop signals / packet cards (`de/components.ts`): trend stages
  (emerging/accelerating/maturing/cooling), Schwarz fit, Readiness, Author
  strength, Beyond citation counts, Reproducibility, Code & artifacts,
  Code released, No code released, Sent as {via}, {n} paper, Sent {date},
  Created {date}.
- Briefing fixtures (`de/briefing.ts`): five edition titles and four
  summary paragraphs, a sample from the log, The full screening log is
  retained….
- Papers/misc (`de/papers.ts`): last {n} days, Signal Score, Formula,
  Variables, Evidence, Why did it score {score}?, How solid is the
  evidence?, the paper-chat fallback paragraph, Search (only reached via
  a BFF label), Schwarz Fit, Run of {date}… .
- Caution: 35 further keys look dead to a naive grep but are reached via
  `t(x.label)` with label arrays (`papers-browser.tsx:22-45`, status maps in
  `scanner-ui.tsx:441-449`) — the test distinguishes these; don't prune by
  grep alone.

### P1.8 Studio area is English-only
- All of `src/app/studio/**` (41 hardcoded strings, static titles
  "Runs"/"Run", nav item "Briefings app") ignores the toggle, but shares the
  shell and account menu with the reading app.
- Action: decide — translate it, or explicitly present it as an
  English-language operator console (and rename "Briefings app").

### P1.9 Word choice — German (second pass)
Register (formal *Sie*) and typography („“, –, …) are right; these are
consistency items:
| English | Current German | Suggestion |
|---|---|---|
| Included / Ingested | both **Aufgenommen** | Ingested → **Erfasst** (two states, one word today: the papers filter header vs the briefing funnel column) |
| Evidence / "how solid the evidence is" | Belege / **Evidenz** | **Belege** throughout (Evidenz is a false friend outside academic German) |
| Schwarz fit / Fit score / "fit and novelty" | Schwarz-Eignung / Fit-Score / Fit | one term — keep **Fit** as the scored dimension, or **Eignung** everywhere |
| Overall score | **Gesamtscore** | **Gesamt-Score** (match Signal-/Fit-/Neuheits-/Mindest-Score) |
| Conversation (Ask history) | **Gespräch(-sverlauf)** | **Unterhaltung** / plain **Verlauf** (German chat-UI convention) |
| Needs review | Prüfung nötig | **Prüfung erforderlich** |
| The answer failed. | Die Antwort ist fehlgeschlagen. | **Die Antwort konnte nicht erstellt werden.** |
| All statuses | Alle Status | **Alle** or **Alle Stufen** (correct Duden plural, reads like a typo) |
| Minimum/Maximum TRL | Minimales/Maximales TRL | **Min./Max. TRL** |
| Screened out | Ausgesiebt | **Aussortiert** (matches "Nothing was screened out" → aussortiert) |

### P1.10 Word choice — English (non-native audience)
- Idioms that don't travel: "deep-dived", "surfaced", "cleared the signal
  bar", "pencil out", "drill in", "dig in" → "analysed in depth", "passed
  the threshold", "open".
- Engineering vocabulary in user copy: backend, endpoint, storage key,
  contract, persisted, reporting step, funnel, turns. (Keep tokens/grounded
  for this audience.)
- Case-duplicate keys: "Signal score"/"Signal Score",
  "Schwarz fit"/"Schwarz Fit", "Headlines"/"Headline stories" — merge.
- Spelling mix: UK in PRODUCT.md ("Rigour") vs US on the login
  ("authorized"). Pick one; en-GB matches the en-GB date choice (P1.2).

---

## P2 — decide with Schwarz Digits

### P2.1 Content-language policy (the big one)
Everything *generated* is English and nothing is configurable:
- Chat: no language instruction in the system prompt
  (`backend/chat/engine/orchestrator.py:73-80`) — a German question gets
  whatever the model chooses. Minimal fix: "Answer in the language of the
  question."
- Briefing narrative (`backend/research_intelligence/tasks/step_7_reporting/`)
  and digest e-mail (`templates/emails/pipeline_digest.html`, subjects in
  `tasks/auxiliary/email_digest.py:228-230`): no language parameter.
  Proposal: a workspace-level `language` field driving both.
- MCP server instructions *mandate* English output
  (`backend/mcp_server/server/app.py:280`) — revisit whether that is a
  product decision or a leftover.
- Recommendation: state the policy in the UI/docs — e.g. "research content
  is shown in the language of its source; the interface is available in
  German and English". English content + German chrome is defensible for a
  paper scanner, but it should be a stated choice.

### P2.2 German backend messages are nearly free
- Django: `LANGUAGE_CODE='en-us'`, `USE_I18N=True`, but **no
  `LocaleMiddleware`** (`django_project/settings.py:98-108, 214`), and the
  BFF forwards only `Authorization` (`frontend/src/lib/api/server.ts:35-42`).
- Consequence: DRF and password-validator messages ("This password is too
  short…") surface verbatim in the German settings form
  (`settings-form.tsx:77-80`). Django ships German translations for all of
  them.
- Action: add `django.middleware.locale.LocaleMiddleware`, forward
  `Accept-Language: de|en` from the BFF based on the `rs-lang` cookie.

### P2.3 Gender-neutral house style
- Current: generic masculine — Staff → **Mitarbeiter**, **Analyst**,
  **Autoren-Stärke**, placeholder "Autor". Schwarz Gruppe corporate German
  uses gender-neutral forms in many channels (Mitarbeitende).
- A style decision to make with the counterparts, then apply in one sweep —
  not a defect.

### P2.4 Naming unification (both languages)
- One name for the daily artefact: today briefing / digest / brief /
  edition → German Briefing / Digest-Archiv / Digest-Zeitplan / Überblick /
  Ausgabe. Proposal: **Briefing** everywhere.
- One name for the Q&A surface: Ask / Assistant / "the scanner" → Fragen /
  Assistent / "Scanner fragen". Proposal: **Ask / Fragen**; drop
  "the scanner".
- The greeting: "Good morning" shows at 16:00 too; fallback `there` →
  "zusammen" addresses a group. Proposal: time-based greeting or
  "Willkommen zurück, {name}".

### P2.5 Language toggle mechanics
- The `rs-lang` cookie is set client-side without `Secure`
  (`src/lib/i18n-client.tsx:19`) and keeps the legacy `rs-` prefix vs the
  `sri_*` session cookies.
- The e2e "bilingual" step toggles twice and asserts nothing
  (`tests_e2e/specs/03_manager_workspace_and_settings.journey.spec.ts:47-51`);
  its locator also matches a menu item labelled "English", which the UI never
  renders (the menu always shows "Deutsch" + switch). Add a real assertion
  (e.g. nav shows "Heute" after toggling).
