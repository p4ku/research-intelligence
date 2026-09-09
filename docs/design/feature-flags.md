# Feature flags: all_papers, stars, ask

Status: shipped (PRs #71, #78, #79, #80 merged 7 Sep 2026; e2e guard follows). Written 2026-09-07.
Update 9 Sep 2026: every flag is **fixed** via a new `fixed?: boolean` on `FeatureDef` — `all_papers: false`, `ask: false`, `stars: true`. A fixed flag ignores the cookie, is never written to it, and has no row; `TOGGLE_KEYS` (the non-fixed flags) drives the menu, and the "Demo features" section does not render while it is empty. Everything below describes the mechanism as built; delete a flag's `fixed` property to put its switch back.
Drift log: re-audited against origin/main 872c1e2 on 2026-09-07 (Home corpus search #61, Briefings ledger #52, Ask composer #66, root 404 #50, settings a11y #64); decisions D1–D4 below folded in.
Scope: `frontend/` only, plus the doc and e2e notes called out in section 5.
This file lives at the repo root (`docs/`), outside `frontend/scripts/scope-check.ts`'s provenance root, so it is committed on its own, not inside the flag PRs.

---

## 1. Summary

Three per-browser demo flags let the product owner hide a feature live, from the account menu, and put it back: `all_papers` (the `/papers` corpus list), `stars` (every star affordance), `ask` (the `/ask` chat canvas and its entry points).

They are stored in one cookie, `rs-features`, written from the browser by the same mechanism as the language toggle (`frontend/src/lib/i18n-client.tsx:17-21`), read server-side by a new `getFeatures()`, and seeded into a client provider by the shell.

Everything defaults ON: an absent, empty or malformed cookie means the whole product. Nothing is in env, in `next.config.mjs`, in the proxy, or in CI.

Off means removed, not disabled: the nav item is gone, every link into the feature is not rendered, and the page itself calls `notFound()` so a pasted URL lands on the shell's not-found card.

The BFF stays live throughout. Hiding is a UI concern; `/bff/papers`, `/bff/stars` and `/bff/chat/*` keep serving, because a cookie the visitor owns is a preference, not an authorization boundary.

---

## 2. Decisions

| Question | Decision | Why |
|---|---|---|
| Source of truth | One cookie, `rs-features`, per browser | Mirrors `rs-lang` (`frontend/src/lib/i18n.ts:13`); flips live with no deploy |
| Cookie namespace | `rs-` (preferences), not `sri_` (session) | `sri_access`/`sri_refresh`/`sri_user` are auth (`frontend/src/lib/auth/cookies.ts:7-12`); `rs-lang` and `rs-stars` are preferences |
| Encoding | A `.`-separated list of the flags that are **off**; all-on is the empty string | Absent cookie = everything on; a new flag is on for browsers carrying an old cookie; unknown tokens ignored. `.` is the house separator (`frontend/src/lib/bff/stars/cookie.ts:18`), picked there because it survives cookie serialisation unencoded |
| Defaults | All three ON, in code | Screenshot harness, skeleton-drift and Playwright all run cookieless and must see the full product |
| Cookie attributes | `path=/; max-age=31536000; samesite=lax`, not `httpOnly` | The toggle writes it with `document.cookie`; copy `rs-lang` exactly (`frontend/src/lib/i18n-client.tsx:19`) |
| Off behaviour for a hidden page | `notFound()` in the page body (and in `generateMetadata`) | House pattern (`frontend/src/app/(sidebar)/papers/[id]/page.tsx:34`) |
| HTTP status of a hidden page | Both `/papers` and `/ask` → **HTTP 200** with the not-found card streamed in place; each route's `loading.tsx` returns null when its flag is off so no skeleton paints first | Both routes have a `loading.tsx` (`/papers` gained one on main on 7 Sep 2026, after the first audit); the 200-in-stream trade is already decided and pinned (`frontend/docs/skeletons.md`, `frontend/scripts/skeleton-drift.ts`). Shipped as PR #78 and #80 |
| BFF routes | Unchanged and live | Hiding is UI; Django is reachable through the proxy rewrite anyway (`frontend/src/proxy.ts`) |
| Env / CI / proxy / middleware | None | `rs-lang` only needs the proxy because it seeds from `Accept-Language`; flags default in code |
| Logout | The cookie is **not** cleared | `rs-lang` and `rs-stars` survive sign-out; the demo state must too |
| Studio | Real switches in its account menu; its page tree pinned all-on by a nested provider | The account menu is shared chrome and must work everywhere; the gallery must not follow a demo cookie, or `skeleton:drift` measures a cookie |
| `rs-stars` cookie when stars are off | Not cleared | Flipping stars back on restores the same stars on the next refresh |

---

## 3. The mechanism, file by file

### 3.1 Registry and codec: `frontend/src/lib/features.ts` (new, pure)

No React, no `next/headers`, no icons: it is imported by server modules, the client provider, the status service and the tests. Shaped like `RESOURCES` in `frontend/src/lib/bff/core/source.ts:48-58` (a `Record<Key, Def>` plus resolvers) so it reads as a familiar object.

```ts
export const FEATURES_COOKIE = 'rs-features'

export type FeatureKey = 'all_papers' | 'stars' | 'ask'

export interface FeatureDef {
  key: FeatureKey
  /** English source string, translated through t() at the call site. */
  label: string
  /** Gettext context for the label, so it reuses an existing German value. */
  ctx?: string
  /** The route this flag owns: the 404 gate and the vanish guard. */
  route?: { href: string; exact: boolean }
}

export const FEATURES: Record<FeatureKey, FeatureDef> = {
  // exact: true. /papers/<id> must survive when the *list* is hidden.
  // 'All papers' already resolves: de/papers.ts:77 and de/ask.ts:53 both hold
  // 'Alle Papers', and the merged dictionary finds it. Add no chrome.ts copy;
  // if one is ever added it must carry that exact string, or the duplicate
  // check at i18n.test.ts:85-96 fails.
  all_papers: { key: 'all_papers', label: 'All papers', route: { href: '/papers', exact: true } },
  // 'Stars' has NO German today (de/components.ts:32 is 'Starred': 'Markiert',
  // not 'Stars'). PR 1 adds Stars: 'Markierungen' to de/chrome.ts.
  stars: { key: 'stars', label: 'Stars' },
  // 'nav|Ask' is already 'Fragen' (de/chrome.ts:9): zero new keys.
  ask: { key: 'ask', label: 'Ask', ctx: 'nav', route: { href: '/ask', exact: true } },
}

export const FEATURE_KEYS = Object.keys(FEATURES) as FeatureKey[]
export type Features = Record<FeatureKey, boolean>
export const ALL_ON: Features = { all_papers: true, stars: true, ask: true }

/** A missing, empty or malformed cookie is simply "everything on". */
export function decodeFeaturesCookie(raw: string | undefined): Features {
  const off = new Set((raw ?? '').split('.').map((s) => s.trim().toLowerCase()))
  return Object.fromEntries(FEATURE_KEYS.map((k) => [k, !off.has(k)])) as Features
}

/** Registry order, so the value never churns between writes. */
export function encodeFeaturesCookie(f: Features): string {
  return FEATURE_KEYS.filter((k) => !f[k]).join('.')
}

/** The one nav-filter rule, unit-testable without rendering the shell. */
export function isVisible<T extends { feature?: FeatureKey }>(item: T, f: Features): boolean {
  return !item.feature || f[item.feature]
}
```

Cookie value alphabet is `[a-z_.]`. The separator is `.`, not a comma, matching `ID_SEP` at `frontend/src/lib/bff/stars/cookie.ts:18`: that codec deliberately chose `.` and `~` because "both characters survive cookie serialisation unencoded" (`:7-11`). A comma is outside RFC 6265's `cookie-octet` set and is the historical `Set-Cookie` splitting character in proxies and edge middleware, so it is the one separator the house precedent rejected. `rs-features=all_papers.ask` means the list and Ask are hidden. The value stays readable in devtools mid-demo, which matters when a flip does not appear to work.

**All-on is the empty string.** `encodeFeaturesCookie(ALL_ON)` returns `''`, written as a present cookie with an empty value (`rs-features=`). The cookie is never deleted, and `decodeFeaturesCookie(undefined)` and `decodeFeaturesCookie('')` are the same state, so an implementer who turns all three back on and sees an empty value in devtools is looking at a successful write, not a failed one.

Note the polarity: the cookie lists what is **off**, the switches show what is **on**. Keep that inversion inside `encodeFeaturesCookie`; it must never reach a component.

### 3.2 Server reader: `frontend/src/lib/features-server.ts` (new)

```ts
import 'server-only'
import { cookies } from 'next/headers'
import { notFound } from 'next/navigation'
import { cache } from 'react'
import { FEATURES_COOKIE, decodeFeaturesCookie, type FeatureKey, type Features } from './features'

/** Deduped per request, like getWorkspacesState (src/lib/workspace-server.ts:28). */
export const getFeatures = cache(
  async (): Promise<Features> => decodeFeaturesCookie((await cookies()).get(FEATURES_COOKIE)?.value),
)

export async function hasFeature(key: FeatureKey): Promise<boolean> {
  return (await getFeatures())[key]
}

/** One line at the top of a flagged page: off means the route does not exist. */
export async function requireFeature(key: FeatureKey): Promise<void> {
  if (!(await hasFeature(key))) notFound()
}
```

`'server-only'` matches `frontend/src/lib/workspace-server.ts:1`. All logic lives in the pure module: no test in this repo mocks `next/headers`, and this should not be the first.

### 3.3 Client provider: `frontend/src/lib/features-client.tsx` (new)

Copies `LanguageProvider` (`frontend/src/lib/i18n-client.tsx:15-25`) exactly, with two deliberate additions.

```tsx
'use client'
import { usePathname, useRouter } from 'next/navigation'
import { createContext, useCallback, useContext, useMemo, useRef } from 'react'
import {
  ALL_ON, FEATURES, FEATURES_COOKIE, decodeFeaturesCookie, encodeFeaturesCookie,
  type FeatureKey, type Features,
} from './features'

// Without a provider (unit renders) every flag reads ON: a component rendered
// in isolation shows its full self.
const FeaturesContext = createContext<{ features: Features; setFeature: (k: FeatureKey, on: boolean) => void }>({
  features: ALL_ON,
  setFeature: () => {},
})

export function FeaturesProvider({ features, children }: { features: Features; children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  // The pathname churns on every navigation; the callback must not.
  const pathRef = useRef(pathname)
  pathRef.current = pathname

  // `features` is a fresh object on every server render, so nothing may depend
  // on its identity. Derive one stable object from the encoded string and use
  // that everywhere: the context value then really does hold across refreshes.
  const encoded = encodeFeaturesCookie(features)
  const stable = useMemo(() => decodeFeaturesCookie(encoded), [encoded])

  const setFeature = useCallback(
    (key: FeatureKey, on: boolean) => {
      const next = encodeFeaturesCookie({ ...decodeFeaturesCookie(encoded), [key]: on })
      document.cookie = `${FEATURES_COOKIE}=${next};path=/;max-age=31536000;samesite=lax`
      // Turning a flag off while standing on the page it owns would 404 the
      // user under their own hands. One hard navigation, not replace+refresh:
      // a single server render, layout and page both fresh, no 404 flash and
      // no client-router-cache question about the shared (sidebar) layout.
      const route = FEATURES[key].route
      const standingOn =
        !on && route && (route.exact ? pathRef.current === route.href : pathRef.current.startsWith(route.href))
      if (standingOn) {
        window.location.assign('/dashboard')
        return
      }
      router.refresh()
    },
    [encoded, router],
  )

  const value = useMemo(() => ({ features: stable, setFeature }), [stable, setFeature])
  return <FeaturesContext.Provider value={value}>{children}</FeaturesContext.Provider>
}

export function useFeatures(): Features { return useContext(FeaturesContext).features }
export function useSetFeature() { return useContext(FeaturesContext).setFeature }
```

Two details in that sketch are easy to get wrong and both are load-bearing. `setFeature` must not close over `features` or `pathname`: both change identity on every render, which would make the callback unstable and the memo pointless no matter what it is keyed on. Keying everything on `encoded` (a string) and reading the pathname from a ref makes `[encoded, router]` an honest dependency list, so no `eslint-disable` is needed. And the vanish guard must be a single hard navigation: `router.replace()` and `router.refresh()` fired in the same tick have no ordering guarantee, so the likely outcome on `/papers` is a 404 card flashing under the owner mid-demo, and the reverse ordering serves the shared `(sidebar)` layout from the client router cache with the stale nav.

Three properties this shape buys, all load-bearing:

- **The inert default is ON.** `frontend/src/components/paper-card.test.tsx:24-29` renders `PaperCard` with `renderToStaticMarkup` and no providers and asserts the star is in the markup. A default-off context breaks that test, and it is the belt to Studio's braces: the nested `ALL_ON` provider (§3.4) is what actually pins the gallery, but a component rendered with no provider at all must still show its full self.
- **No local state.** The value comes from the server prop, so it changes only when the refreshed render commits. That is what makes a flip **atomic**: client-rendered stars and server-rendered stars disappear in the same commit. Adding optimistic state so the Switch animates instantly would stagger the flip and change several conclusions below; do not.
- **The vanish guard.** `router.refresh()` alone refreshes `/papers` or `/ask` into their own 404. `stars` owns no route, so it has no guard and always takes the plain-refresh path, the same path the language toggle takes.

Cost of copying the language shape honestly: the Switch does not move until the refresh lands. On a slow connection that reads as lag. Accepted, because the alternative breaks atomicity.

### 3.4 Seeding the two shells, and threading the flags below them

`frontend/src/app/(sidebar)/layout.tsx:21-25` becomes:

```tsx
// Flags first: it is a cookie read, no I/O. Then keep today's parallel shape
// (layout.tsx:21 already races the language and stars reads) so the shell's
// one Django-adjacent call does not start a microtask later than it does now.
const features = await getFeatures()
const [lang, starred] = await Promise.all([
  getLang(),
  // Don't pay for the stars read when stars are hidden.
  features.stars ? stars.get().catch(() => emptyStars) : Promise.resolve(emptyStars),
])
return (
  <ApplicationLayout lang={lang} features={features} user={user}>
    <StarsProvider initial={starred}>{children}</StarsProvider>
  </ApplicationLayout>
)
```

`emptyStars` must be the module constant from `frontend/src/lib/bff/stars/schema.ts`, not an inline `{ papers: [], briefings: [] }`: `StarsProvider` re-seeds by reference comparison (`frontend/src/lib/stars-client.tsx:47-50`), so a fresh object every render would discard in-flight optimistic state when stars come back.

`frontend/src/app/studio/layout.tsx:19-23` must call `getFeatures()` and pass it too, **and** pin its own subtree all-on:

```tsx
const [lang, features] = await Promise.all([getLang(), getFeatures()])
return (
  <ApplicationLayout lang={lang} features={features} user={user} area="studio">
    {/* The account menu (inside ApplicationLayout) shows the real switches, so
        the operator can flip flags from here. Everything Studio renders is
        pinned all-on by this nested provider: the skeleton gallery must show
        every shape whatever the demo cookie says, and skeleton:drift must
        never measure a cookie. Nested context wins for the subtree. */}
    <FeaturesProvider features={ALL_ON}>{children}</FeaturesProvider>
  </ApplicationLayout>
)
```

`ALL_ON` is a plain-boolean constant from the pure module, so a server layout can pass it across the boundary. This is the whole Studio rule, stated once: **the menu sees the real values, the page tree sees `ALL_ON`.** `frontend/src/app/studio/skeletons/page.tsx` needs no edit at all, both panes of every pair stay all-on, and the non-goal in §5 ("the gallery is flag-blind") becomes true by construction instead of by hope. `ApplicationLayout`'s `features` prop is **required**, exactly like `lang`, so TypeScript catches a shell that forgets it.

`frontend/src/app/layout.tsx` needs no change: it reads the language only for `<html lang>`, and flags have no document-level effect.

**Threading the flags below the shell.** Client components read `useFeatures()` and need no prop: `PaperCard` (`frontend/src/components/paper-card.tsx:1`), `EditionBrowser` (`frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:1`), `BriefingLedger` (`frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:1`), `EditionPaperList`, `PapersBrowser`, `PaperChat` and the `error.tsx` boundaries are all `'use client'`. Server components and skeletons take **one prop, `features: Features`**, not one boolean per flag, introduced by PR 2 and merely *consumed* by PR 3 and PR 4, so each of these signatures is edited once and not three times:

| component | prop | why |
|---|---|---|
| `PaperHeader` (`papers/[id]/paper-header.tsx:61`) | `features: Features = ALL_ON` | The gallery renders it directly (`studio/skeletons/page.tsx:444`) with no such prop; a required prop fails `bun run typecheck` there |
| `PaperHeaderSkeleton` (`paper-header.tsx:100`) | `features: Features = ALL_ON` | Gallery renders it at `:445` |
| `PaperNav`, `PaperNavSkeleton`, `PaperNavFrame` (`papers/[id]/paper-nav.tsx:28,82,99`) | `features: Features = ALL_ON` | Gallery renders both at `:453-462` and `:463` |
| `EditionBrowserSkeleton` (`briefing-archive/edition-browser.tsx:413`) | `features: Features = ALL_ON` | Gallery renders it at `:551` with only `editions`/`papers`/`briefParagraphs`. The file moved with the archive split (#52): the reading room is `/briefing-archive` now |
| `BriefingLedgerSkeleton` (`briefing/briefing-ledger.tsx:295`) | `features: Features = ALL_ON` | New with the ledger (#52). The gallery renders it at `studio/skeletons/page.tsx:538-541` with only `rows`/`domains`, so this prop is optional for exactly the reason `EditionBrowserSkeleton`'s is |
| `PaperRecord` (`papers/[id]/sections.tsx:54`), `PaperRecordSkeleton` / `PaperPageSkeleton` (`papers/[id]/skeletons.tsx:23,71`) | `features: Features` (required) | Nothing outside the route renders them, so a required prop is free and catches a missed call site |
| `EditionHead` (`briefing/[date]/sections.tsx:29`), `EditionHeadSkeleton` / `EditionPapersSkeleton` / `EditionPageSkeleton` | `features: Features` (required) | Same |
| `EditionsSkeleton` (`briefing-archive/skeletons.tsx:7`), `LedgerSkeletonRegion` (`briefing/skeletons.tsx:10`), and `BriefingPageSkeleton` **twice**: the ledger's (`briefing/skeletons.tsx:19`) and the archive's (`briefing-archive/skeletons.tsx:16`) | `features: Features` (required) | Same, but note the doubling: the archive split left two files exporting `BriefingPageSkeleton`, one per route, each read by its own `loading.tsx`. PR 3 edits both, or one route's bones disagree with its page |
| `DashboardSkeleton` (`dashboard/skeletons.tsx:48`) | `features: Features` (required) | It renders the **real** `<CorpusSearch domains={[]} />` at `:52`, so D1 makes it a flag consumer. `dashboard/loading.tsx` is its only caller and is where the read goes |

The default is `ALL_ON` rather than `true`-per-flag for the same reason the context default is: a component rendered in isolation shows its full self. Every source of the prop is a page or a `loading.tsx` calling `getFeatures()` once, so a Suspense fallback and its content can never disagree mid-stream.

### 3.5 Nav filtering and the dropdown: `frontend/src/components/application-layout.tsx`

`ShellNavItem` (`:48-54`) gains `feature?: FeatureKey`; `coreNav` (`:58-64`) tags `/papers` with `all_papers` and `/ask` with `ask`. `studioNav` (`:66-69`) is never tagged.

One line in `ApplicationLayoutInner` (near `:175`):

```ts
const features = useFeatures()
const nav = NAVS[area].filter((item) => isVisible(item, features))
```

The `.map` at `:251-260` is untouched, and so is the prefix-highlight expression inside it (`:255`). This is the single render site for both the desktop rail and the mobile drawer: `frontend/src/components/sidebar-layout.tsx:64,68` mounts the same `sidebar` node twice. Filtering here covers both; filtering in a rail-only branch would leave the row in the drawer.

The toggle rows go under the Deutsch row (`:102-118`), using the section/heading pair already exported at `frontend/src/components/dropdown.tsx:92,108`. Two diff details so PR 1 is exactly what this section shows: `AccountDropdownMenu` currently calls only `useLanguage()` and `useT()` (`:93-94`), and the file's dropdown import (`:6-13`) does not yet include `DropdownSection`/`DropdownHeading`.

```tsx
// application-layout.tsx:6-13: extend the existing import
import {
  Dropdown, DropdownButton, DropdownDivider, DropdownHeading,
  DropdownItem, DropdownLabel, DropdownMenu, DropdownSection,
} from '@/components/dropdown'

// ...at the top of AccountDropdownMenu, beside the two hooks already there:
const features = useFeatures()
const setFeature = useSetFeature()

// ...and in the JSX, after the Deutsch row's <DropdownDivider />:
<DropdownDivider />
<DropdownSection>
  <DropdownHeading>{t('Demo features')}</DropdownHeading>
  {FEATURE_KEYS.map((key) => {
    const Icon = FEATURE_ICONS[key]
    const def = FEATURES[key]
    return (
      <DropdownItem
        key={key}
        onClick={(e: React.MouseEvent) => {
          // preventDefault keeps the Headless UI menu open, so two flags can
          // be flipped without reopening (same trick as :104-105).
          e.preventDefault()
          setFeature(key, !features[key])
        }}
      >
        <Icon />
        <DropdownLabel>{t(def.label, def.ctx)}</DropdownLabel>
        <Switch as="span" checked={features[key]} color="dark/zinc" className="pointer-events-none ml-auto" />
      </DropdownItem>
    )
  })}
</DropdownSection>
```

`FEATURE_ICONS` stays in this client file, beside the nav icons, for the same serialisability reason documented at `:71-75`. **Reuse the icons the file already imports** rather than adding a 16px set: `DocumentTextIcon` and `ChatBubbleLeftRightIcon` are already imported from `@heroicons/react/20/solid` (`:37,:39`) for `coreNav`, so importing the 16px namesakes is a duplicate-identifier error. Add only `StarIcon` to that same 20/solid block. `DropdownItem` sizes icons itself via `*:data-[slot=icon]` (`frontend/src/components/dropdown.tsx:75`), so the visual difference against the 16px `LanguageIcon` on the Deutsch row is nil. Type the map to match `ShellNavItem.Icon` (`:51`):

```ts
const FEATURE_ICONS: Record<FeatureKey, React.ComponentType<{ className?: string }>> = {
  all_papers: DocumentTextIcon, stars: StarIcon, ask: ChatBubbleLeftRightIcon, // all @heroicons/react/20/solid
}
```

Two constraints on the rows:

- **Four locators constrain the row labels, and only four.** The nav locators are anchor-scoped (`nav a:has-text('Papers')` at `tests_e2e/pages/SidebarNav.ts:19`, `nav a:has-text('Ask')` at `:21`), and the toggle rows are `button`s inside a portalled `[role='menu']`, so an "Ask" or "All papers" row cannot match them. What a label must not collide with is `menuSettingsItem` (`SidebarNav.ts:27`, matches "Settings"/"Einstellungen"), `menuLanguageToggle` (`:28`, "Deutsch"/"English"), `menuSignOutButton` (`:29`, "Sign out"/"Abmelden"), each `.first()`, so a colliding label turns spec 03 red on a flags-on run, and `WorkspaceSwitcher.workspaceItems` (`tests_e2e/pages/WorkspaceSwitcher.ts:19`), which reads every `[role='menu'] [role='menuitem']` as a workspace name if a menu is already open (`:38-52`). Judge any future copy change against those four selectors, not against a blanket ban.
- **The rows are never hidden.** They are how a feature comes back. They also appear in the Studio account menu, because `AccountDropdownMenu` is shared chrome mounted twice from `ApplicationLayoutInner` (`:206-216` navbar, `:268-287` sidebar footer, both behind the `mounted` guard at `:181-185`). Check once on a laptop viewport that the taller menu (Settings + Deutsch + heading + three rows + Sign out, `min-w-64` at `:96`) still fits when anchored `top start` from the footer, which is the one the owner will use.

### 3.6 Page opt-in and 404 behaviour

One line, first statement of the page body:

- `frontend/src/app/(sidebar)/papers/page.tsx` → `await requireFeature('all_papers')`
- `frontend/src/app/(sidebar)/ask/page.tsx` → `await requireFeature('ask')`

Both pages are `export const dynamic = 'force-dynamic'`, so nothing changes about caching, and there is no cached variant to worry about when the cookie flips.

`generateMetadata` runs independently of the page component, so gate it too:

- `frontend/src/app/(sidebar)/papers/page.tsx:12-15` → return `{}` when off, or the 404's tab reads "Papers".
- `frontend/src/app/(sidebar)/ask/page.tsx:12-15` → return `{}` when off. The tab then falls back to the root default "Research Intelligence" (`frontend/src/app/layout.tsx:32-35`), which needs no new i18n key.

**Do not gate `frontend/src/app/(sidebar)/papers/[id]/page.tsx`.** `all_papers` hides the list; paper detail is reached from briefings, Home and chat citations. That is why `FEATURES.all_papers.route.exact` is `true`: a prefix rule would take detail down with the list and misfire in the vanish guard.

**Status codes differ, and the doc must say so.**

- `/papers` gained a `loading.tsx` on main on 7 Sep 2026 (the `--stream` negative control moved to `/settings`), so like `/ask` it streams the shell with **HTTP 200** and renders the not-found card in place. Its `loading.tsx` returns null when `all_papers` is off (shipped in PR #78). Nothing about this work gives either route a real 404 status.
- `/ask` has a `loading.tsx`, so Next streams the shell with **HTTP 200** and renders the segment's not-found card in place. This is the decided house trade (`frontend/docs/skeletons.md:147-149`), the same shape as a dead `/papers/[id]` or `/runs/[id]` permalink, and it is asserted by `frontend/scripts/skeleton-drift.ts:234-257` (`res.status === 200 && copy`). Accept it. Deleting `ask/loading.tsx` to force a hard 404 turns `bun test` red at `frontend/src/app/loading-convention.test.ts:35`, because `ask/page.tsx` is force-dynamic and is not in `KNOWN_UNCOVERED`, and that list "may only shrink".
- Gate `frontend/src/app/(sidebar)/ask/loading.tsx` to `return null` when the flag is off. The file stays (so the convention test still finds it), and the Ask skeleton stops being the first painted body of a hidden route's response. It is not a sub-frame flash: it is what `skeleton:drift --not-found` inspects.

Both cases land on `frontend/src/app/(sidebar)/not-found.tsx`, inside the shell, so the account menu survives and the flag can be flipped back on from the 404 itself.

`frontend/src/app/(sidebar)/not-found.tsx:20-33` hard-links to `/papers`, so with `all_papers` off the 404 offers a button to another 404. It is a server component that already awaits `getT()` under a layout that already reads cookies (`(sidebar)/layout.tsx:21`) and every page in the group is `force-dynamic`, so it can `await getFeatures()` and drop the Papers button, promoting Briefings. **This belongs in the plumbing PR**, because `ask` off is what makes that page a routine demo surface. Two notes for the implementer. A `cookies()` read inside a not-found boundary is the one place Next has historically tripped on prerendering, so PR 1's verify list includes a `bun run build` that must show no "used `cookies` inside a component that was statically rendered" warning for this file. And on PR 1 alone the CTA filter is a deliberate half-state: flipping `all_papers` off removes the "Go to Papers" button while `/papers` is still live and still in the nav. That lasts exactly one PR, until PR 2 gates the route.

There is a **second** 404 page and it also hard-links to `/papers`. `frontend/src/app/not-found.tsx:34` is the root not-found added by #50: the only page a URL that matched no route at all can reach. It renders **outside** the shell, so there is no account menu on it and no way to flip a flag back on from it, which makes an unexplained button to another 404 worse here than in the shell. It is an async server component that already awaits `getT()` (`:17`) and nothing above it is static, so `await getFeatures()` is available exactly as it is in the sidebar card: with `all_papers` off, drop the `t('Go to Papers')` link at `:37` and let the `/dashboard` button at `:28` stand alone as the primary CTA. **This lands in PR 1 beside the sidebar one** (decision D4, 7 Sep 2026), and it carries the same `bun run build` check: no "used `cookies` inside a component that was statically rendered" warning for this file either. It also corrects a claim in the tables below: `de/errors.ts:46` (`'Go to Papers'`) now has two callers, not one.

A hidden route 404s wherever you arrive from, including immediately after sign-in: the proxy remembers the requested path on the way to login (`frontend/src/proxy.ts:183-191`), `safeNext` hands it back (`frontend/src/lib/auth/safe-next.ts:2-15`, `frontend/src/app/auth/login/route.ts:103`), and `frontend/src/lib/auth/leave.ts:41-43` does the same on a mid-session 401. Leave all three alone: `safeNext` is a security helper about origin, not product surface, and teaching it about flags would make it async and break its unit test's shape.

### 3.7 `/bff/status` exposure

`bffStatus()` is the "what is this build actually doing" endpoint and is already `force-dynamic` (`frontend/src/app/bff/status/route.ts`), so a cookie read costs nothing:

```ts
// src/lib/bff/status/service.ts: extend BffStatus (:33-40)
features: Features   // { all_papers: boolean; stars: boolean; ask: boolean }
// ...in the return object (:103-116), with `const f = await getFeatures()`
features: await getFeatures(),   // shipped shape (PR #71): the plain Features object; defaults are always on, so no per-key default field
```

It reflects **the calling browser's** cookie, not a server setting: say so in a comment, or someone reads it as global config. The per-resource `RESOURCES` report is untouched: `stars` and `chat` keep appearing even with their flags off, because that section describes the seam to Django, not the UI. Since #61 it carries one entry more than this doc's first draft assumed: the composed `search` resource behind Home's typeahead (`frontend/src/lib/bff/core/source.ts:57-59`, `BFF_SOURCE_SEARCH`, `supports: ['composed']`), which is not flag-gated either, for the same reason.

### 3.8 Tests

The runner is `bun test` (`frontend/package.json`), not vitest, despite the house note. Everything below is `bun:test`, matching `frontend/src/lib/bff/stars/cookie.test.ts`.

`frontend/src/lib/features.test.ts` (new), all against the pure module:

- round trip: `decode(encode(f)) === f` for all eight combinations;
- `decode(undefined)`, `decode('')`, `decode('   ')` → `ALL_ON`;
- unknown and malformed tokens ignored: `decode('ask.not_a_flag..ASK')` turns off only `ask` (asserts trim + lowercase);
- `encode(ALL_ON) === ''`, and `decode('')` round-trips back to `ALL_ON`;
- `encode` emits registry order regardless of key order in the object;
- `isVisible` with plain objects (no React, no icons);
- **registry i18n coverage:** every `FEATURES[k]` label (with its context) is a key in `de`. The static scanner at `frontend/src/lib/i18n.test.ts:52-53` only matches string *literals* inside `t(...)`, so `t(def.label, def.ctx)` is invisible to it, exactly like the nav labels. This assertion is what closes that hole, and it is why `Stars: 'Markierungen'` must land in `de/chrome.ts` in the same PR, or PR 1 fails its own new test on its own branch (`All papers` and `nav|Ask` already resolve; `Stars` is the one that does not exist anywhere in `src/locales/de/`).

`frontend/src/app/flagged-routes.test.ts` (new), a convention test in the style of `frontend/src/app/loading-convention.test.ts`: a literal map `{ '(sidebar)/papers/page.tsx': 'all_papers', '(sidebar)/ask/page.tsx': 'ask' }`, read each file, assert it contains `requireFeature('<key>')`. Cheapest way to keep the gate from being lost in a refactor; rendering a server page in `bun test` is not something this repo does.

`getFeatures` itself gets no unit test: it would need a `next/headers` mock. The codec carries the risk.

E2E: `tests_e2e/specs/07_feature_flags.journey.spec.ts` plus a `tests_e2e/pages/FeatureToggles.ts` page object is the only end-to-end guard, and it must be **its own branch/PR**: `frontend/scripts/scope-check.ts:17` fails `bun run check` on anything outside `frontend/`. It must assert **absence** with raw locators, never `SidebarNav.navigateTo`: that helper falls back to `goto(path)` when the nav link is missing (`tests_e2e/pages/SidebarNav.ts:63-75,89-101`), so a flag-off assertion written through it would "succeed" into the 404.

---

## 4. The flags

### 4.1 `all_papers`

**Semantics.** The `/papers` corpus browser stops existing as a destination while individual papers stay readable. The route calls `notFound()` before any data work, so a pasted URL renders the shared not-found card inside the shell (streamed inside an HTTP 200, because the route has a `loading.tsx` that returns null when the flag is off). The Papers item is filtered out of the nav (rail and drawer). Home's `<CorpusSearch>` typeahead is removed whole (decision D1, 7 Sep 2026), not merely its submit path: every row the panel offers is a corpus destination (`/papers`, `/papers?q=`, `/papers/<id>`), so a field left behind would be a field with nowhere to go. One side effect belongs in the open, not in a discovery mid-demo: the panel's `Ask about “{title}”` row goes with it, so `all_papers` off also removes Home's only Ask entry point, whatever the `ask` flag says. The shared 404 card drops its "Go to Papers" button. On `/papers/[id]` every list-derived affordance goes: the "Papers" breadcrumb, the prev/next arrows, the "{n} of {total}" position, and the `neighboursOf()` corpus fetch that feeds them, but the row itself stays with a redirected back link, because with the crumb gone it would otherwise be the app's only reachable route with no exit and no current nav item (nav highlighting is prefix-based, `frontend/src/components/application-layout.tsx:255`). The record itself is untouched; what changes is everything that told the reader where they were. `/papers/[id]` stays reachable from briefings, Home's TopPapers, `/tuning` and chat citations, and it 404s on its own for a bad id. Skeletons must agree with their pages or the shell flashes chrome that then vanishes. Hiding is UI-only: `/bff/papers` and `papers.listEverywhere`/`listAll` keep serving briefings, Ask's picker, scoring and status. Ask's attach-a-paper picker stays; it lists the corpus to scope a conversation, renders no `/papers` href, and since #66 is fed by its own route (`GET /bff/papers/palette`), which stays live like every other BFF surface. The i18n rule is "keep every existing key, drop callers freely": `frontend/src/lib/i18n.test.ts:78` hard-fails on a used-but-missing key and only warns on a dead one. And the off state is deliberately anonymous (`frontend/src/app/(sidebar)/not-found.tsx:6-8` says the card is generic), so a hidden route is indistinguishable from a broken link, to a viewer and to automation alike.

**Touchpoints** (sorted by file).

| file:lines | what | when off |
|---|---|---|
| `.claude/skills/screenshots/SKILL.md:15,55` | Screenshot skill's route inventory, incl. `/papers`, `/papers/[id]` | No change (outside `frontend/`, `scope:check` fails). Name in the PR description |
| `docs/user_journeys/route_matrix.md:53,65,68,69` | Root route matrix's `/papers` row and query params | No change (outside `frontend/`). Already stale: `?run_id` is unimplemented |
| `frontend/README.md:33` | Home bullet: "one search across every paper" | Add the flag clause: the whole search typeahead is removed when `all_papers` is off. The bullet still applies, but the search it names is now a panel of corpus destinations, not a plain field |
| `frontend/README.md:41` | Route inventory, Papers bullet | Add: behind the `all_papers` preference; 404s when off |
| `frontend/README.md:51-52` | The "Bilingual UI … switched from the user menu" bullet | Add the sibling bullet for the three per-browser feature switches. Editing 41 without this leaves the README describing one preference mechanism when there are two |
| `frontend/docs/design.md:80` | "Sidebar shell — core nav (Dashboard, Papers, Trends, Watchlist, Tuning)" | No change. Already stale; listed so a doc sweep does not "fix" it into a second source of truth about the nav |
| `frontend/docs/skeletons.md:79-82` | The `--stream /papers` boundary-free control runbook prose | Add a clause: flag-off, `--stream /papers` fails for the wrong reason (a 404 with no boundaries), which reads like the assertion working |
| `frontend/docs/skeletons.md:135-140` | Pass-3 paragraph: the nav row and the cached `papers.listAll` neighbours | Both are gone when the flag is off; this paragraph goes stale first |
| `frontend/docs/skeletons.md:221-224` | "Still on KNOWN_UNCOVERED: /papers" | Note the control route is now flag-gated. The passage moved down with the archive-split entry added at `:209-217` |
| `frontend/scripts/lib/browser.ts:63-65` | `ctx.addCookies([{ name: 'rs-lang', … }])`, the only preference seed for scripted runs | No change now. It is the mechanical proof that scripted runs get the ON default, and the single place a `--features` seed would go (importing `FEATURES_COOKIE`, not re-hardcoding the name) |
| `frontend/scripts/screenshots.ts:178-193` | The `nav-open` pseudo-route: opens the mobile drawer | No change. This is the frame that proves the nav filter reached the drawer; include it in any flag-off before/after pair |
| `frontend/scripts/screenshots.ts:194-206,223-226` | The `search-open` pseudo-route (new with #61): it fills Home's combobox with a query (`getByRole('combobox', { name: 'Search papers' })` at `:202`), waits for the listbox at `:203`, and shoots the open panel; registered in `PSEUDO_ROUTES` at `:223-226` | **Exclude it from every flag-off run.** With `all_papers` off the combobox is never rendered, so the locator never resolves, the shot hangs to its timeout and then sets `failed = true` (`:415`), failing the whole sweep for a route that is correctly absent. A flag-off pass must pass `--routes` without `search-open` |
| `frontend/scripts/screenshots.ts:210-211` | `SCREENS` entries `papers` and `paper-detail` | No change. Do not add flag-off variants: filenames are `SCREENS.indexOf(screen)+1` (`:351`), so inserting renumbers every later shot and breaks comparison with `docs/i18n/shots/*/manifest.json`. Capture flag-off as a separate `--out` run |
| `frontend/scripts/screenshots.ts:278` | `discover()` (declared `:253`) scrapes the paper `[id]` from `/papers` | No change today (cookieless run). If a flag-off sweep is ever wanted, give it a `/dashboard` fallback like the briefing lookup already has at `:275-277` |
| `frontend/scripts/screenshots.ts:408-412,415,423`, summary `:460` | A shot with HTTP ≥ 400 sets `failed = true` and exits 1; a thrown shot (`:415`) does the same | No change. Correct the folklore: a flag-off run fails **loudly** on `/papers` and logs the skipped paper-detail shot; the risk is a broken review loop, not a silent one. The `search-open` row above is the second way a flag-off run goes red |
| `frontend/scripts/skeleton-drift.ts:13` | `--not-found /papers/<uuid>` example | No change and no flag interaction: that permalink is paper **detail**, which stays alive. The `--stream /papers` control lives in `frontend/docs/skeletons.md`, not here |
| `frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:332` | The archive reader links each paper at `/papers/${p.id}` | No change. This is the main argument for keeping `/papers/[id]` alive. The file moved with the ledger split (#52); the ledger's own rows link to `/briefing/[date]`, not to papers |
| `frontend/src/app/(sidebar)/dashboard/home-ui.tsx:43-50` | `HomeLinks` contains only the briefings link, `t('All briefings →')` at `:47` | No change. There is no "All papers →" link on Home; the `de/dashboard.ts:24` key is dead already |
| `frontend/src/app/(sidebar)/dashboard/home-ui.tsx:101-110` | TopPapers links `/papers/${p.id}` | No change; detail stays reachable |
| `frontend/src/app/(sidebar)/dashboard/page.tsx:31-36,59` | Home awaits several things in one `Promise.all` (`:31-36`), then renders `<CorpusSearch domains={domains} suggestions={scanTopics(state.all)} />` at `:59` | Add `getFeatures()` to the `Promise.all` and render `{features.all_papers && <CorpusSearch …/>}` (decision D1). The whole typeahead goes, not just its submit; and with it Home's Ask row |
| `frontend/src/app/(sidebar)/dashboard/run-card.tsx:192-196` | "{domain} is running. Briefings and papers stay available meanwhile." | Judgement call, recommendation: no change. It is about data availability during a run, not the list route; a variant costs a new German key and a features read in a card with nothing else to do with the flag |
| `frontend/src/app/(sidebar)/dashboard/skeletons.tsx:48-56` | `DashboardSkeleton` (declared `:48`) renders the **real** `<CorpusSearch domains={[]} />` at `:52`, not a bone | Must match the page. Add the required `features: Features` prop of §3.4 and skip the search; `dashboard/loading.tsx` is the only caller and must read `getFeatures()`. A skeleton that kept the field would paint a live search above a hidden corpus |
| `frontend/src/app/(sidebar)/not-found.tsx:20-33` | The shared 404 card; primary button "Go to Papers" → `/papers` | Drop the Papers button and promote Briefings. Server component, so `await getFeatures()`. Landed in the plumbing PR |
| `frontend/src/app/(sidebar)/papers/error.tsx:6-24` | Route error boundary for the list | No change. `notFound()` raises the not-found signal, not an error, so it never fires while the flag is off |
| `frontend/src/app/(sidebar)/papers/page.tsx:12-15` | `generateMetadata` returns `{ title: t('Papers') }` | Return `{}` when off, or the 404's tab and history entry read "Papers" |
| `frontend/src/app/(sidebar)/papers/page.tsx:21-35` | The list route: resolves `?q=`, reads workspace state, fetches the corpus | `await requireFeature('all_papers')` as the first statement, **above** the `state.kind` check, so a hidden page 404s even during a workspace outage. Keep `dynamic = 'force-dynamic'` and add no `loading.tsx` |
| `frontend/src/app/(sidebar)/papers/page.tsx:50-55` | `<PapersBrowser key={q ?? ''} …>` | No change for this flag. Noted because the existing `key` is the house lever for remounting the browser, relevant to the stars mid-flip fix |
| `frontend/src/app/(sidebar)/papers/papers-browser.tsx:58-666` | The whole client browser (`PapersBrowser` declared `:58`), which since #61 ranks through `@/lib/search/match` (`:19`, `:118-160`) and shows a `ScreeningHint` (`:298-300`, declared `:522`) | No change. Unreachable, not conditional. Do not thread a flag into it |
| `frontend/src/app/(sidebar)/papers/[id]/error.tsx:14-22` | Back link `{ href: '/papers', label: t('Back to Papers') }`; copy names "the list" | Client component, so `useFeatures()`. Point back at `/briefing` with `t('Go to Briefings')` (or `/dashboard` with `t('Back to Today')`, `de/chrome.ts:50`), and swap the description for the neutral "Nothing was lost. Try again in a moment." already in `de/chrome.ts` |
| `frontend/src/app/(sidebar)/papers/[id]/loading.tsx:9-11` | Renders `PaperPageSkeleton` | Read `getFeatures()` and thread the flag down |
| `frontend/src/app/(sidebar)/papers/[id]/page.tsx:32-50` | Breadcrumbs: `{ label: t('Papers'), href: '/papers' }` plus the streamed title crumb | Drop the whole `<Breadcrumbs>` element when off (see judgement calls), and thread the flag to **both** `PaperRecordSkeleton` (the Suspense fallback at `:55`) and `PaperRecord` (`:60`). `PaperPageSkeleton` is loading.tsx's, not this file's |
| `frontend/src/app/(sidebar)/papers/[id]/paper-nav.tsx:28-52` | `PaperNavFrame` renders `<div data-row="pager" className="flex items-center gap-1">` **unconditionally**, containing a `px-1.5` `<span>` for the position | Takes the same optional `features: Features = ALL_ON` prop and withholds the whole pager div, mirroring `PaperHeaderFrame`'s `{action && …}` guard at `paper-header.tsx:56`. Passing `null` for prev/position/next is not enough: the empty div and its 12px span still sit opposite the back link under `justify-between` |
| `frontend/src/app/(sidebar)/papers/[id]/paper-nav.tsx:82-97` | `PaperNav`: back link `/papers` with `t('All papers')` at `:87-90`, prev/next arrows, "{n} of {total}" | Takes `features: Features = ALL_ON` (optional, because the gallery calls it with no such prop at `studio/skeletons/page.tsx:453-462`). Keep the row, swap the back link at `:87-90` to `/briefing` (`t('Go to Briefings')`) or `/dashboard` (`t('Back to Today')`), and pass the flag to `PaperNavFrame` so the pager goes. Deleting the row removes the only in-page exit from a paper opened from Home or a chat citation |
| `frontend/src/app/(sidebar)/papers/[id]/paper-nav.tsx:99-113` | `PaperNavSkeleton`; its back slot at `:103-107` also reads `t('All papers')` | Keep the export (the gallery renders it at `:463`), take the same optional prop, and swap the back label **here too**. If the skeleton keeps "All papers" while the loaded row says "Go to Briefings", the two widths differ, `/papers/[id]` reflows on every load and the `data-row="back"` pair drifts |
| `frontend/src/app/(sidebar)/papers/[id]/sections.tsx:29-32` | `PaperCrumb` streams the title and returns **null** on a miss | Why the crumb trail is dropped wholesale: a one-item trail whose only label can be null renders an empty `<nav>` bar |
| `frontend/src/app/(sidebar)/papers/[id]/sections.tsx:38-52` | `neighboursOf()` fetches `papers.listAll` and derives prev/next/position | Do not call it. Skipping the request is the point, not ignoring the result |
| `frontend/src/app/(sidebar)/papers/[id]/sections.tsx:54-65` | `PaperRecord({ id, t, lang })` renders `<PaperNav …>` at `:65` | The **signature** at `:54` gains the required `features: Features`; `:65` is only the render site. Strict TypeScript makes this a compile-forced edit on a line separate from the render |
| `frontend/src/app/(sidebar)/papers/[id]/sections.tsx:129-133` | Provenance footer (declared `:135-142`) links `/runs/<id>` | No change; that is Runs |
| `frontend/src/app/(sidebar)/papers/[id]/skeletons.tsx:71-84` | `PaperPageSkeleton` repeats the Papers crumb at `:76` and renders `PaperRecordSkeleton` (which includes `PaperNavSkeleton` at `:27`) | Mirror the page exactly: no crumb trail, and a nav row matching the loaded one. Both `PaperPageSkeleton` and `PaperRecordSkeleton` signatures take the flag |
| `frontend/src/app/(sidebar)/tuning/page.tsx:118` | Links a scoring example at `/papers/${id}` | No change; detail, not the list, and `/tuning` is already out of nav |
| `frontend/src/app/(sidebar)/ask/ask.tsx:908` | `t('All papers')` as a chat **scope** label (also `history-sidecar.tsx:152`) | No change. Same English string, different meaning. Do not delete the key from `de/papers.ts` or `de/ask.ts` on that basis |
| `frontend/src/app/(sidebar)/ask/sections.tsx:14-38` | `AskSection` fetches **no** corpus since #66: one `papers.get(paper)` at `:25` resolves a `?paper=` deep link, and nothing else | No change. Governed by the `ask` flag. The picker's corpus is client-side now (`ask/use-palette.ts:35` → `GET /bff/papers/palette`), so `all_papers` off still removes no Django traffic from `/ask`, for a new reason |
| `frontend/src/app/bff/scoring/README.md:12` | "The paper detail page (`/papers/[id]`) still explains a single paper's score from its own metrics" | No change. It names detail, not the list, so the flag does not stale it. Listed so a doc sweep does not treat it as a second route inventory |
| `frontend/src/app/bff/papers/README.md:7-19` | Lists the resource's consumers: the Papers list, paper detail, briefings, scoring and, since #66, the Ask palette route | One line: the list consumer is UI-flagged, the endpoint is not. Do not flag the palette line with it: that consumer belongs to Ask |
| `frontend/src/app/bff/papers/palette/route.ts:12`, `frontend/src/lib/bff/papers/{corpus,palette}.ts` | Ask's corpus, its own route since #66: `recentCorpus()` slimmed by `toPalette()` | No change, unreachable from here and stays live. It is why `all_papers` off removes no Ask traffic: the picker fetches this route, not `/bff/papers` |
| `frontend/src/app/bff/papers/route.ts` | `GET /bff/papers` | No change, stays live. Nothing in the app fetches this route from the client today (its client-side siblings are `/bff/papers/palette` and `/bff/search`), so leaving it exposes no UI |
| `frontend/src/app/bff/search/route.ts:8-9`, `frontend/src/app/bff/search/README.md` | `GET /bff/search`, the typeahead's endpoint (new with #61) | No change, stays live, ungated by design, exactly like `/bff/papers`. Nothing calls it once the field is hidden, and the cookie is a preference, not an authorization boundary |
| `frontend/src/lib/bff/search/{service,assemble,schema,corpus,contract,fixtures}.ts`, `frontend/src/lib/search/match.ts`, `frontend/src/lib/bff/contract.ts:13,25` | The search service, its ranking, and the `searchOperations` contract entry | No change, unreachable when the search is hidden. The flag must never be read below the page layer, and `match.ts` is the papers browser's ranker too |
| `frontend/src/app/bff/stars/README.md:7-8` | Names `/papers` among the star-toggle consumers | One line: that consumer is behind the `all_papers` preference |
| `frontend/src/app/loading-convention.test.ts:13-18` | `(sidebar)/papers/page.tsx` is listed debt; the list may only shrink | No change, and do not add a `loading.tsx` to `/papers`. Keep the `force-dynamic` export or the page silently drops off the scan |
| `frontend/src/app/studio/layout.tsx:19-23` | The second caller of `ApplicationLayout` | Must pass real `features` from `getFeatures()`. No nav change (`studioNav` has no `/papers`), but the shared account menu shows the switches, and a defaulted prop would show them in the wrong position |
| `frontend/src/app/studio/skeletons/page.tsx:448-466` | The gallery's `paper-nav` pair (`<PaperNav neighbours t/>` at `:453-462`, `<PaperNavSkeleton t/>` at `:463`), plus borrowed `PaperHeader` (`:444`), `ScoreRail` (`:476-490`) and `PaperCard` (`:275`) | **No edit to this file.** `PaperNav`, `PaperNavSkeleton` and `PaperNavFrame` take an optional `features: Features = ALL_ON`, so every call here compiles unchanged and renders the full product, and Studio's own subtree is pinned all-on by the nested provider in `studio/layout.tsx` (§3.4). The flag reaches the component only from `PaperRecord`/`loading.tsx` |
| `frontend/src/app/bff/chat/stream/route.ts:92-110` | `resolveScope()` builds a citation `href: '/papers/{id}'` at `:107`, behind the `if (!body.paper_id)` early return at `:96`; the POST handler is `:21-86` | No change. Listed because it is one of the two producers of a `/papers/<id>` link inside Ask answers; detail stays alive, so nothing breaks |
| `frontend/src/components/application-layout.tsx:48-54` | `ShellNavItem` | Add `feature?: FeatureKey` |
| `frontend/src/components/application-layout.tsx:58-64` | `coreNav`; `/papers` is line 61 | Tag `feature: 'all_papers'`. Do not mutate the array |
| `frontend/src/components/application-layout.tsx:84-140` | `AccountDropdownMenu` | Where the three toggle rows go. The `all_papers` row stays visible when its own flag is off |
| `frontend/src/components/application-layout.tsx:175,251-260` | `const nav = NAVS[area]` then `nav.map(...)`; the prefix highlight is `:255` | Filter with `isVisible`. Removes the row from rail and drawer, and with it the prefix highlight for `/papers*` |
| `frontend/src/components/corpus-search/corpus-search.tsx:129-133,181,186,191` | The typeahead itself: an empty submit goes to `/papers` (`:129`), an exact id to `/papers/<id>` (`:131`), anything else to `papersHref(q)` (`:133`); focus prefetches `/papers` (`:181`) and warms `GET /bff/search` (`:186`); the live status reads `t('Opening Papers…')` (`:191`) | No change, unreachable when the search is hidden. Listed so the implementer gates the search **once**, at the two render sites of D1, and not five more times inside the component |
| `frontend/src/components/corpus-search/rows.ts:42-43,54-58,82,89,178` | `papersHref()` (`:42-43`), the `openPapers()` section (`:54-58`), the paper rows to detail (`:82`, `:178`) and the "See all {n} papers" row to `/papers?q=` (`:89`) | No change, unreachable when the search is hidden. The one row in this file that does **not** come for free is the Ask row (`:60-75`); it is gated for its own flag in §4.3 |
| `frontend/src/components/corpus-search/panel.tsx:133` | The results panel renders `t('Open Papers')` for the `papers` row | No change, unreachable when the search is hidden |
| `frontend/src/components/page-nav.tsx:29-45` | The numbered pager; its only caller in the app is `papers-browser.tsx:339` | No change. It stops rendering because its caller is unreachable. Do not thread the flag into it, do not delete it |
| `frontend/src/components/paper-card.tsx:108` | `<Link href={`/papers/${paper.id}`}>` | No change; it links to detail |
| `frontend/src/components/paper-card.test.tsx:12-33` | Asserts the detail href | No change |
| `frontend/src/components/search-frame.tsx` | The shared search chrome (new with #61), used by Home's search, the papers browser and the archive browser | No change. It is a frame, not a destination: two of its three users stay live with the flag off |
| `frontend/src/lib/auth/safe-next.ts:2-15` | The single sink for post-auth destinations; consumers at `auth/login/route.ts:103`, `auth/logout/route.ts:21`, `lib/auth/leave.ts:41-43` | No change. Sign-in from a bounced `/papers` link lands on the 404, which is the off behaviour. This is the one chokepoint if that is ever judged wrong; filtering here would make a sync pure helper async |
| `frontend/src/lib/bff/chat/fixtures.ts:85-92` | `fixtureStreamFrames` hardcodes a citation `href: '/papers/${PAPER.id}'` for **every** stubbed stream | No change. Listed because under `BFF_SOURCE_CHAT=stub`, the likely demo sourcing, even a corpus-scoped Ask answer shows a `/papers/<id>` citation. It resolves to detail, which stays alive |
| `frontend/src/lib/bff/core/source.ts:28,57-59` | The `search` resource added by #61 (`BFF_SOURCE_SEARCH`, `supports: ['composed']`) | No change. Data sourcing is a different axis from the demo flag, and `/bff/status` reports the resource whatever the cookie says (§3.7) |
| `frontend/src/lib/bff/papers/service.ts:125-172` | `listEverywhere()` and `list()`; `listAll` feeds briefings, scoring, status, the detail pager | No change. The flag must never be read below the page layer |
| `frontend/src/lib/i18n-client.tsx:15-25` | The toggle shape being copied: write cookie, `router.refresh()` | Copying it verbatim refreshes `/papers` into its own 404. Hence the vanish guard in §3.3 |
| `frontend/src/lib/i18n.ts:13` | `LANG_COOKIE = 'rs-lang'` | No change. The precedent for the cookie name and attributes |
| `frontend/src/lib/i18n.test.ts:78-114` | Used-but-missing fails; dead keys warn | No change. This is why the rule is "keep the key, drop the caller". Note the nav labels are **already** dead keys: the scanner cannot see `t(label, 'nav')` at `application-layout.tsx:258`, so filtering the nav item changes nothing here |
| `frontend/src/lib/i18n.test.ts:85-96` | No conflicting duplicates across area modules | Constrains the toggle-row labels. `All papers` already exists as `Alle Papers` in `de/papers.ts:77` and `de/ask.ts:53`; bare `Papers` exists three times. Reuse the existing German verbatim or use a context key |
| `frontend/src/lib/bff/stars/cookie.ts:15-16` | `STARS_COOKIE = 'rs-stars'`, httpOnly, written server-side | No change. Corrects the premise: two preference precedents exist with opposite mechanics. The flag cookie must follow `rs-lang` (client-written, not httpOnly) or the toggle silently writes nothing |
| `frontend/src/locales/de/chrome.ts:8` | `'nav\|Papers'` | Keep. Already has no static caller |
| `frontend/src/locales/de/chrome.ts:35` | `"Couldn't load papers."`, the list error boundary's heading | Keep. Its caller can never fire while the page 404s |
| `frontend/src/locales/de/chrome.ts:51` | `'Back to Papers'`, only caller is `papers/[id]/error.tsx:21` | Keep; the caller becomes conditional |
| `frontend/src/locales/de/dashboard.ts:24` | `'All papers →'` | No change. Verified dead already |
| `frontend/src/locales/de/dashboard.ts:94` | Home's old search placeholder | Keep, and note it is **already** dead, independently of this work: since #61 Home's placeholder resolves through `de/components.ts:48`, whose caller is `components/corpus-search/corpus-search.tsx:238`. `'Search papers'` (`de/papers.ts:18`) still has a caller in `papers-browser.tsx` |
| `frontend/src/locales/de/errors.ts:46` | `'Go to Papers'`, with **two** callers since #50: `(sidebar)/not-found.tsx:25` and the root `src/app/not-found.tsx:37` | Keep the key, drop both callers. PR 1 gates them together (decision D4); `'Go to Dashboard'` at `:48` is the root card's fallback primary and needs no change |
| `frontend/src/locales/de/papers.ts:1-72` | The list-only half of the dictionary | No change. Every key still has a static caller; the scanner reads source, not reachability |
| `frontend/src/proxy.ts:36-43,59-64,148-163` | `LANG_COOKIE_OPTIONS`, `detectLang()`, the first-visit seed, `withLang`/`nextWithLang` | No change, and this entry says why: the language cookie needs proxy seeding only because its default comes from `Accept-Language`. Flag defaults live in code, so "no cookie" already means ON |
| `frontend/src/proxy.ts:183-191` | `toLogin()` stores `?next=` for a signed-out visit | No change. A bounced `/papers` link lands on the 404 after sign-in. Decide it here rather than discovering it mid-demo |
| `frontend/src/proxy.ts:208-214,216-224` | `replaceCookie` and the matcher | No change. `replaceCookie` preserves every cookie it is not replacing, so `rs-features` rides through the refresh path untouched |
| `tests_e2e/README.md:15,77` | Describes `SidebarNav` as traversing `/papers`, and advertises `specs/papers.spec.ts` | No change (outside `frontend/`). Note that `specs/papers.spec.ts` does not exist: the README line and the `run_frontend_e2e.sh:75-76` filter are pre-existing dead infrastructure, not flag interactions |
| `tests_e2e/pages/LoginPage.ts:57` | Post-login check ORs several paths incl. `/papers` | No change; login redirects to `/dashboard` |
| `tests_e2e/pages/PapersPage.ts:15-50` | `goto('/papers')`, `isLoaded()` = URL contains `/papers` **and** `main` visible | No change. Correct the coupling: this goes **green** on the 404 (the card renders inside the shell's `<main>`, `frontend/src/components/sidebar-layout.tsx:82`), `getPapersCount()` returns 0, and spec 02 guards its only real assertion behind `if (paperCount > 0)`. A false green, not a failure |
| `tests_e2e/pages/SidebarNav.ts:19,63-75` | `navPapers` locator (`:19`); `navigateTo('papers')` falls back to `goto('/papers')` | No change. The fallback is why flag coverage must use raw locators |
| `tests_e2e/specs/02_analyst_daily_review.journey.spec.ts:30-38`, `06_end_to_end_researcher_flow.journey.spec.ts:39-41` | The two journeys that visit `/papers` | No change. They are the reason the cookieless default must be ON |

**Judgement calls.**

1. **Home's search.** Remove the whole `<CorpusSearch>` when the flag is off (settled 7 Sep 2026, decision D1) rather than keeping the field and repointing it at `/ask`. Every row the panel can offer is a corpus destination, so a field left behind would be a field with nowhere to go; and repointing would change what the search means (a chat prompt, not a corpus filter) and couple two flags, since Ask may itself be off. The guard is two render sites, `dashboard/page.tsx:59` and `dashboard/skeletons.tsx:52`, and its accepted cost is that Home's `Ask about “{title}”` row disappears with the panel.
2. **`PaperNav` on `/papers/[id]`.** Keep the row, redirect the back link, drop the pager and the position (recommended). Deleting the whole row leaves a paper opened from Home or a citation with no exit at all, since the crumb trail is also going. Keeping the pager is worse: "{n} of {total}" is a claim about a list the reader can no longer open.
3. **The breadcrumb.** Drop the whole `<Breadcrumbs>` element (recommended) rather than leaving a single title crumb that can be null, or substituting a "Briefings" crumb that implies a provenance the page does not know. Do it in `page.tsx` and `skeletons.tsx` together.
4. **The `/bff/papers` route.** Stays live (recommended). Nothing in the app fetches it client-side, and it is shared with detail, briefings, Ask and status.
5. **`safeNext` / post-login landing.** Leave it flag-blind (recommended). A hidden route 404s wherever you arrive from.
6. **The run-card copy** ("Briefings and papers stay available meanwhile"). Leave it (recommended); it is true, and a variant costs a key plus a features read in an unrelated card.

**Open questions for the product owner.**

- Settled 7 Sep 2026: Home's whole search typeahead disappears with the list, and its `Ask about “{title}”` row with it (judgement call 1, decision D1).
- Do you want the `/papers` off state to look deliberate? Today it renders the generic "We couldn't find that" card, so a hidden route is indistinguishable from a dead link.
- Two people watching the demo on two laptops see different navs, and a second tab already open keeps its Papers item until it navigates. Confirm that is fine.

### 4.2 `stars`

**Semantics.** No analyst-facing curation affordance exists in the reading app. No star control renders: no corner `StarButton` on paper cards or archive rail rows, no per-row `StarButton` in the briefings ledger, no `StarToggle` in the paper-detail masthead, the edition masthead or the archive reader header. No Starred filter exists: the **four** `StarredChip`s disappear (the papers browser, the briefings ledger, the archive rail and the edition paper list), and (this is the part that is easy to get wrong) the `starredOnly` state is **forced false**, not merely deprived of its control. In the ledger that state lives in the URL rather than in React, which changes how it is forced but not that it must be. The sidebar layout does not call `stars.get()` and seeds `StarsProvider` with the module constant `emptyStars`. No skeleton reserves space for a star. Nothing is removed server-side: `/bff/stars` GET/PUT keep working, the service, codec, schema and contract entries are untouched, `stars` keeps appearing in `/bff/status`, and the `rs-stars` cookie is **not** cleared, so flipping back on restores the analyst's stars on the next refresh. There is no page to 404: stars own no route, so the `notFound()` rule does not apply to this flag. The flip is **atomic** because `FeaturesProvider` derives from a server prop (§3.3): client-rendered stars and server-rendered ones vanish in the same commit. Gating happens at call sites, and the reason is React hooks, not CSS: a component that returns `null` emits no DOM node and opens no flex gap, but an early return inside a mounted `StarButton` would change its hook count on the very re-render the flip causes. Three call sites must withhold the element itself rather than let it render null. The first is `PaperHeaderFrame`'s `{action && <div className="shrink-0">…}` (`frontend/src/app/(sidebar)/papers/[id]/paper-header.tsx:56`), where `action` is truthy regardless of what the star renders. The second is `ReaderFrame`'s required `star` slot in the archive (`frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:91`), where the attribute must stay and only the value may go. The third arrived with the ledger (#52): `frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:34-35` gives the star a dedicated 28px table column, so the whole column leaves `COLUMNS` (`:47`) and header, cell and skeleton footprint follow from that one edit (decision D2). A star that merely renders null there leaves an empty gutter on every row of the table. Finally, note what the flip actually looks like, and note that the answer depends on the pointer. `StarButton` is `opacity-0` until hover on a **fine** pointer only: `frontend/src/components/star.tsx:68` also carries `pointer-coarse:opacity-100`, so on a touch device the corner star is always visible and the flip is plainly visible on paper cards, archive rail rows and ledger rows too. On a laptop the unmistakable surfaces are still `/papers/[id]` and `/briefing/[date]`, where `StarToggle` is a labelled, always-visible control, plus the ledger, which loses a whole column and so changes width. i18n needs no change: every `t()` call stays in source, merely unrendered.

**Touchpoints** (sorted by file). Two briefing routes carry stars now and they are different work: `/briefing` is the ledger #52 shipped, `/briefing-archive` is the reading room it replaced (reachable by URL only, out of the nav). The ledger's rows come first below, then the archive's at their shifted lines, and PR 3 must do both, including **both** `loading.tsx` files.

| file:lines | what | when off |
|---|---|---|
| `frontend/docs/backend-handoff.md:59` | The P2 ask for per-user stars in Django | No change. A demo toggle is not a change to the backend ask |
| `frontend/docs/conventions.md` | House patterns | Add the feature-flag convention once (cookie, provider, defaults-on, call-site gating, skeleton props). One section, written by whoever lands the plumbing PR |
| `frontend/docs/skeletons.md:62,177-179` | Rule 4 ("add the pair to /studio/skeletons") and the gotcha "a component that renders `null` in several branches must not get a bone that reserves space" | Add one line: a bone a feature flag can hide takes an optional boolean defaulting to `true`, so the gallery keeps its bones and `skeleton:drift` stays green, while the app's `loading.tsx` and Suspense fallbacks pass the flag. This is the rule the star bones bend, the ledger's per-row footprint included |
| `frontend/scripts/skeleton-drift.ts` | Measures `[data-pair]` geometry on `/studio/skeletons?motion=static`; also visits real routes via `--stream`/`--not-found`, signed in | Unchanged and green, because the gallery renders stars-on. It will **not** catch a flag-off skeleton drifting from its flag-off component: the star bones carry no `data-row` marker. Verify those by eye or by screenshot |
| `frontend/src/app/bff/stars/README.md` | The resource README | One line under "How it works today": the UI can be hidden per browser by the `stars` flag, in which case the layout does not call the service and `rs-stars` is left intact |
| `frontend/src/app/bff/stars/route.ts` | `GET`/`PUT /bff/stars` | Unchanged and functional. Leaving it alone is what makes flipping back on instant |
| `frontend/src/app/bff/status/route.ts` | `GET /bff/status` | Unchanged |
| `frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:34-35,47,75,90-98` | The ledger's star column: `COL.star` is a dedicated 28px column (`:34-35`), `'star'` is the first entry of `COLUMNS` (`:47`), its header label is deliberately empty (`:75`), and the header row renders from that list (`:90-98`) | **Withhold the whole column** (decision D2, 7 Sep 2026): drop `'star'` from `COLUMNS` when stars are off and header, cells and skeleton footprint all follow from one edit. This is the third withhold-for-layout site; a star that renders null here leaves a 28px gutter on every row |
| `frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:128-132` | Each row's `<TableCell className={COL.star.cell}>` wrapping `<StarButton kind="briefing" id={row.id}/>` at `:130` | Not rendered, because the column is gone. Do not leave an empty `<TableCell>` behind: the body would then be one cell wider than the header |
| `frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:170` | The expanded-brief row spans `colSpan={COLUMNS.length}` | No edit needed **if** the column leaves `COLUMNS`, which is the argument for gating there rather than at the cell. Check it on a flag-off render anyway: a stale `colSpan` is what makes an open brief overhang the table |
| `frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:186,193,196,201-203,210,213-221` | `useStars()` (`:196`); `starredOnly` lives in the **URL**, read through `useSearchParams` → `stateFrom` (`:201-203`) and written by `window.history.replaceState` inside `update()` (`:213-221`), with the `syncUrl` prop at `:186,193`; the star clause reaches `filterRows` at `:210` | **Force the derived value**: `const starred = features.stars && state.starred`, then read that everywhere `state.starred` is read today. Accept that `?starred=1` survives in the URL, because the ledger does not own the address bar: a reload with the flag off must still show the full list, which is exactly what forcing the derived value gives |
| `frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:223-227` | The three-way `emptyCopy`, including `t('Nothing starred in this domain.')` (German at `locales/de/briefing.ts:7-11`) | Keep all three `t()` calls in source; the dictionary guard reads source, not reachability. With the value forced false, only the first branch is reachable |
| `frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:250-255` | The head's `<StarredChip …/>`, bound to `state.starred` | Not rendered. It is one of the four chips |
| `frontend/src/app/(sidebar)/briefing/briefing-ledger.tsx:295-301,322,325-328` | `BriefingLedgerSkeleton` (declared `:295`) reserves the starred chip with `Bone.Chip width={82}` (`:322`) and every row's star with `<span className="flex size-7"/>` (`:325-328`) | Both bones drop behind the **optional** `features: Features = ALL_ON` of §3.4, optional because the gallery renders this skeleton directly at `studio/skeletons/page.tsx:538-541`. The footprint must go with the column, or the bones are one cell wider than the loaded row |
| `frontend/src/app/(sidebar)/briefing/loading.tsx:5-8` | The **ledger's** instant loading state: renders `<BriefingPageSkeleton t={t}/>` | Add the flag read, pass `stars` down. There are two files with this shape and this name since #52; this is the `/briefing` one |
| `frontend/src/app/(sidebar)/briefing/page.tsx:32,39,44` | The ledger page: `PageHeader` (`:32`), the `LedgerSkeletonRegion` fallback (`:39`) and `LedgerSection` (`:44`) | Read the flag in the existing `Promise.all` (`:28`) and pass it to the fallback. The page stays reachable; stars own no route |
| `frontend/src/app/(sidebar)/briefing/sections.tsx:16-41` | `LedgerSection` composes the rows and renders `<BriefingLedger …/>` at `:40` | Deliberately unchanged: `BriefingLedger` is `'use client'` (`briefing-ledger.tsx:1`) and reads `useFeatures()` itself. Named so it is knowingly untouched rather than overlooked |
| `frontend/src/app/(sidebar)/briefing/skeletons.tsx:10-16,19-25` | `LedgerSkeletonRegion` (`:10-16`) and the ledger's own `BriefingPageSkeleton` (`:19-25`), both rendering `<BriefingLedgerSkeleton/>` | Thread the required `features: Features` through both |
| `frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:77-96` | `ReaderFrame`'s prop is declared **required**: `star: ReactNode` at `:91`, destructured at `:81`, rendered in `<div className="flex shrink-0 items-center gap-3">{star}{link}</div>` at `:110-113` | Pass `star={features.stars ? <StarToggle …/> : null}` at the `:312` call site. `ReactNode` admits `null` under strict mode, so that type-checks against the required prop, but **omitting the attribute does not**: it is a `tsc --noEmit` error and `bun run check` fails at the typecheck step. If the skeleton is to omit it instead, relaxing to `star?: ReactNode` becomes a required edit, not polish. The same trap does **not** apply to `PaperHeaderFrame`'s `action` (`paper-header.tsx:34`), which is already optional |
| `frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:151-152` | `RAIL_ROW` carries `pr-9` to clear the row's corner star | No change. The residual gutter is invisible (nothing visible occupied it) and removing it is churn outside the flag's blast radius. It is a **shared** class, so drift is not the constraint |
| `frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:204-238` | `useStars()` (`:204`), `starredOnly` (`:208`), `starredCount` (`:211-214`), the star clause in `filtered` (`:219`), the `starredOnly ? null : …` active-edition fallback (`:230-233`), `emptyCopy` (`:235-238`) | **Force the value**: `const starredOnly = features.stars && starredOnlyState`. The archive has no Reset control, so a mid-flip with the filter engaged leaves `filtered` starred-only, `active` null, and both panes showing "Nothing starred yet." with no way back short of a hard reload |
| `frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:312` | Reader header passes `star={<StarToggle kind="briefing" id={active.runId} className="shrink-0"/>}` | `star={features.stars ? <StarToggle …/> : null}`: the attribute stays, the value goes. The file is `'use client'` (`:1`), so `useFeatures()` reads directly |
| `frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:351-356` | Rail head `<StarredChip …/>` beside the "{n} of {total} briefings" count | Not rendered. `justify-between` with one child is fine |
| `frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:388` | Each rail row's corner `<StarButton kind="briefing" …/>`, a sibling of the row button | Not rendered. Keep the wrapping `<li className="group relative">`: the group also drives the row's hover background |
| `frontend/src/app/(sidebar)/briefing-archive/edition-browser.tsx:413,445,468` | `EditionBrowserSkeleton` (declared `:413`) reserves the reader star (`:445`) and the rail chip `Bone.Chip width={82}` (`:468`) | Both bones drop behind the optional `features: Features = ALL_ON` prop of §3.4; pass `star={null}` for the reader bone. This skeleton is a **client** component (`:1` is `'use client'`), so a cookie read was never available here; the prop is what keeps `/studio/skeletons` all-on regardless of where the provider mounts |
| `frontend/src/app/(sidebar)/briefing-archive/loading.tsx:5-8` | The **archive's** instant loading state: renders `<BriefingPageSkeleton t={t}/>` from its own `skeletons.tsx` | Add the flag read, pass `stars` down. Missing this file is the easiest omission in PR 3, because it looks identical to the ledger's |
| `frontend/src/app/(sidebar)/briefing-archive/page.tsx:31,35-46` | `PageHeader` (`:31`) plus the `EditionsSkeleton`/`EditionsSection` Suspense pair (`:35-46`) | Read the flag in the existing `Promise.all` (`:27`) and pass it to the fallback. The page stays reachable, by URL only |
| `frontend/src/app/(sidebar)/briefing-archive/sections.tsx:9-51` | `EditionsSection` builds `browserEditions` and renders `<EditionBrowser …/>` at `:50` | Deliberately unchanged: `EditionBrowser` reads `useFeatures()` itself. Named so it is knowingly untouched rather than overlooked |
| `frontend/src/app/(sidebar)/briefing-archive/skeletons.tsx:7-13,16-23` | `EditionsSkeleton` (`:7-13`) and the archive's `BriefingPageSkeleton` (`:16-23`), both rendering `<EditionBrowserSkeleton/>` with no props | Thread the required `features: Features` through both |
| `frontend/src/app/(sidebar)/briefing/[date]/edition-paper-list.tsx:13-18` | `'use client'` solely because the Starred filter reads the star store | Stays client. Do not fork it into a server variant under the flag |
| `frontend/src/app/(sidebar)/briefing/[date]/edition-paper-list.tsx:20-24,51-55` | `starredOnly` (`:21`), `shown = starredOnly ? starred : papers` (`:24`), the "Nothing starred yet." block (`:51-55`) | **Force the value**: `const shown = features.stars && starredOnly ? starred : papers`. Otherwise a mid-flip leaves the edition showing only the starred subset with no control to clear it. Keep the `t('Nothing starred yet.')` call in source |
| `frontend/src/app/(sidebar)/briefing/[date]/edition-paper-list.tsx:34-38` | The section header's `<StarredChip …/>` | Not rendered, so the header is count + log link |
| `frontend/src/app/(sidebar)/briefing/[date]/loading.tsx:8-11` | Renders `<EditionPageSkeleton t lang/>` | Add `getFeatures()` and pass `stars` down. The instant skeleton has no other way to know |
| `frontend/src/app/(sidebar)/briefing/[date]/page.tsx:40,55-79` | The two Suspense pairs: `EditionHeadSkeleton`/`EditionHead`, `EditionPapersSkeleton`/`EditionPapers` | Read the flag once in the existing `Promise.all` and pass it to both fallbacks and to `EditionHead`, so a fallback and its content cannot disagree mid-stream |
| `frontend/src/app/(sidebar)/briefing/[date]/sections.tsx:29-42` | `EditionHead({ wsId, date, lang, t, domains })`, a server component taking no flag | The **signature** at `:29` gains the required `features: Features`, and `page.tsx:65` must forward it. A compile-forced edit on a line separate from the render site |
| `frontend/src/app/(sidebar)/briefing/[date]/sections.tsx:67-72` | `EditionHead` renders `<StarToggle kind="briefing" id={edition.run_id}/>` beside the title | Not rendered; the h1 fills the row |
| `frontend/src/app/(sidebar)/briefing/[date]/sections.tsx:90-112` | `EditionPapers({ wsId, date, lang })` renders `<EditionPaperList …/>` | Deliberately unchanged: `EditionPaperList` is `'use client'` and reads `useFeatures()`. Note the split: two sections in one file, gated by different mechanisms on purpose |
| `frontend/src/app/(sidebar)/briefing/[date]/skeletons.tsx:54-55` | `EditionHeadSkeleton`'s star bone `h-[30px] w-28` | Drop behind the required `features: Features` (nothing outside the route renders it). Otherwise the skeleton promises a 112px control that never arrives |
| `frontend/src/app/(sidebar)/briefing/[date]/skeletons.tsx:99-100` | `EditionPapersSkeleton`'s `Bone.Chip width={82}` for the Starred filter | Drop, same prop |
| `frontend/src/app/(sidebar)/briefing/[date]/skeletons.tsx:127-133` | `EditionPageSkeleton` composes both | Thread the boolean through |
| `frontend/src/app/(sidebar)/layout.tsx:3-6,19-24` | Imports `emptyStars`, `stars`, `StarsProvider`; awaits `getLang()` and `stars.get()`; wraps children in `<StarsProvider initial={starred}>` | Skip the fetch: `initial={features.stars ? await stars.get().catch(() => emptyStars) : emptyStars}`. Keep the provider mounted (it is inert on an empty set) and pass the **module constant** so the reference-comparison reseed at `stars-client.tsx:47-50` behaves |
| `frontend/src/app/(sidebar)/papers/page.tsx:50-55` | `<PapersBrowser key={q ?? ''} …>` | No change recommended. Listed because widening the key to `` `${q ?? ''}\|${stars}` `` is the house lever if the owner wants every filter reset on a flip |
| `frontend/src/app/(sidebar)/papers/papers-browser.tsx:70,73,131,179,187,208,226,326-333` | `useStars()` (`:70`), the `starredOnly` state (`:73`), the filter clause (`:131`), `starredCount` (`:179`), `filterKey` (`:187`), `filtersActive` (`:208`), `resetFilters` (`:226`) and the empty-copy branch (`:326-333`) | **Force the value** at the top: `const starredOnly = features.stars && starredOnlyState`. Every downstream memo, key and branch then follows. Without it, a flip taken with the chip active leaves the list silently narrowed, the Reset link showing with no chip to explain it, and possibly the "unreachable" `t('Nothing starred yet.')` on screen with stars off |
| `frontend/src/app/(sidebar)/papers/papers-browser.tsx:304-308` | `<StarredChip …/>` in the results count line, beside the Reset link at `:309-313` | Not rendered. Reset stays, driven by `filtersActive` |
| `frontend/src/app/(sidebar)/papers/[id]/loading.tsx:9-11` | Renders `<PaperPageSkeleton t={t}/>` | Add the flag read and pass `stars` |
| `frontend/src/app/(sidebar)/papers/[id]/page.tsx:33,55,60` | Reads `[{id}, t, lang]` in a `Promise.all`; renders `<PaperRecordSkeleton t={t}/>` as the Suspense fallback and `<PaperRecord …/>` as content | Read the flag here and pass it to **both**. Without this file the whole prop chain has no source: `PaperHeader` never reads cookies |
| `frontend/src/app/(sidebar)/papers/[id]/paper-header.tsx:61,95` | `PaperHeader({ paper, t, lang })` (`:61`) passes `action={<StarToggle kind="paper" …/>}` (`:95`) | Takes the **optional** `features: Features = ALL_ON` of §3.4, optional because the gallery calls `<PaperHeader paper t lang="en"/>` with no such prop at `studio/skeletons/page.tsx:444`, and a required one fails typecheck there. Then `action={features.stars ? <StarToggle …/> : undefined}`. This is the one call site where withholding the element is a **layout** requirement: `PaperHeaderFrame`'s `{action && <div className="shrink-0">…}` at `:56` would otherwise render an empty flex item and open a 20px gap on mobile |
| `frontend/src/app/(sidebar)/papers/[id]/paper-header.tsx:100-118` | `PaperHeaderSkeleton` (declared `:100`) reserves the star with `action={<Bone.Block className="h-[30px] w-24"/>}` | Drop behind the **optional** `features: Features = ALL_ON`, so the gallery's `<PaperHeaderSkeleton/>` at `studio/skeletons/page.tsx:445` compiles and keeps its bone |
| `frontend/src/app/(sidebar)/papers/[id]/sections.tsx:54,69` | `PaperRecord({ id, t, lang })` renders `<PaperHeader paper t lang/>` | Consumes the required `features: Features` added to `:54` by PR 2 and forwards it at `:69`. PR 3 adds no signature here, which is the point of threading one object |
| `frontend/src/app/(sidebar)/papers/[id]/skeletons.tsx:23,31,71,81` | `PaperRecordSkeleton({ t })` renders `<PaperHeaderSkeleton/>` at `:31`; `PaperPageSkeleton({ t })` renders `PaperRecordSkeleton` at `:81` | **Both signatures** must gain the flag and `:81` must forward it, or the reads added to `page.tsx:55` and `loading.tsx` have no path to the bone |
| `frontend/src/app/layout.tsx:5,67` | The shared sonner `<Toaster/>` | Unchanged. Shared with Ask and other flows, not stars-only |
| `frontend/src/app/studio/layout.tsx:13-25` | The Studio shell; mounts no `StarsProvider` | Passes the real `features` to `ApplicationLayout` (so the switches work) **and** wraps its children in `<FeaturesProvider features={ALL_ON}>` (§3.4), which is what keeps the gallery's loaded panes stars-on |
| `frontend/src/app/studio/skeletons/page.tsx:271-277,440-446,526-543,545-557` | The **four** gallery pairs whose loaded pane shows a star: `paper-card` (`<PaperCard/>` at `:275`), `paper-header` (`:444`, skeleton `:445`), `briefing-ledger` (`<BriefingLedger syncUrl={false}/>` at `:531-535`, skeleton `:538-541`) and `edition-browser` (`:549`, skeleton `:551`) | **No edit to this file.** All eight panes stay all-on because `studio/layout.tsx` wraps Studio's children in `<FeaturesProvider features={ALL_ON}>` (§3.4), so the `useFeatures()` gates inside `PaperCard` (`paper-card.tsx:109`), `BriefingLedger` (`briefing-ledger.tsx:128-132,250-255`) and `EditionBrowser` (`briefing-archive/edition-browser.tsx:312,351,388`) read ON here whatever the demo cookie says, while the skeleton props default to `ALL_ON` too. Without that nested provider the loaded panes would lose their stars while the skeleton bones stayed, and `bun run skeleton:drift` would fail its 4px desktop gate on `paper-header`, `briefing-ledger` and `edition-browser` for anyone who opened `/studio` mid-demo, green today only because the drift run is cookieless |
| `frontend/src/components/application-layout.tsx:104-119` | The Deutsch row | Not a stars touchpoint to hide; it is where the stars switch goes. `coreNav` has no stars item |
| `frontend/src/components/paper-card.tsx:41-52` | `PaperCardFrame`'s optional `corner` slot and the meta row's `pr-8` | No change. `corner` is already optional and absolutely positioned. Leave `pr-8`: invisible, and shared with the skeleton |
| `frontend/src/components/paper-card.tsx:109` | Passes `corner={<StarButton kind="paper" …/>}` | `corner={stars ? <StarButton …/> : undefined}`. The file is `'use client'`, so `useFeatures()` reads directly, with no prop threading through `papers-browser` or `edition-paper-list` |
| `frontend/src/components/paper-card.test.tsx:24-29` | Renders `PaperCard` with **no provider** and asserts `aria-label="Star this paper"` is present and emitted after `</a>` | Must keep passing. This is the test that pins the default-on context. Optionally add a sibling case rendering inside a features-off provider and asserting the label is absent: the cheapest regression guard for the flag |
| `frontend/src/components/star.tsx:40-175` | `StarButton`, `StarToggle`, `StarredChip` | An optional belt-and-braces guard, but it **must sit after every hook**, immediately before the JSX: `StarButton` calls `useStars`, `useStarLabels`→`useT`, `usePop`→`useState` (`:49-52`); `StarToggle` `:96-100`; `StarredChip` `:152`. An early return before them is a `react-hooks/rules-of-hooks` error under `bun run lint` and, because the flip re-renders mounted instances, a live "Rendered fewer hooks than expected" crash |
| `frontend/src/lib/bff/core/source.ts:27,58` | `'stars'` in `ResourceName` (`:27`) and the `BFF_SOURCE_STARS` registry entry (`:58`) | Unchanged. Deploy-time data sourcing is a different axis from the demo flag |
| `frontend/src/lib/bff/status/service.ts:24-40` | `bffStatus()` walks `RESOURCES` and probes Django | Unchanged. `stars` stays listed even with the UI flag off; hiding it would misreport the seam to the backend team |
| `frontend/src/lib/bff/stars/contract.ts:5-49` | The four registry operations, generated into `frontend/contract/*.openapi.json` | Unchanged. Touching it regenerates both artifacts and fails `bun run lint` for no reason |
| `frontend/src/lib/bff/stars/cookie.ts:15-52` | The `rs-stars` codec | Unchanged, and the cookie is deliberately not cleared |
| `frontend/src/lib/bff/stars/cookie.test.ts` | Codec unit tests | Unchanged |
| `frontend/src/lib/bff/stars/schema.ts:9-39` | `Stars`, `StarKind`, `StarUpdate`, `emptyStars`, `applyStar` | Unchanged; `emptyStars` is the off-seed |
| `frontend/src/lib/bff/stars/service.ts:23-46` | The cookie-backed stub or the Django pass-through | Unchanged, simply not called. With `BFF_SOURCE_STARS=django` this is a real round-trip on every shell render that the flag-off layout skips |
| `frontend/src/lib/i18n-client.tsx:7-24,31-33` | `LanguageProvider` holds **no** client state | The file that decides two of this flag's hazards. Because the provider derives from a server prop, the flip is atomic and a mounted `StarButton` re-renders rather than unmounting mid-flight. A provider with optimistic local state would stagger the flip and turn the in-component guard into a live crash |
| `frontend/src/lib/i18n.test.ts:78-113` | The dictionary guard | Unchanged and green, because gating is conditional rendering, not deletion. Note it will **not** catch over-aggressive removal: a deleted call site only produces a tolerated dead-key warning |
| `frontend/src/lib/stars-client.tsx:20-81` | `StarsProvider`, optimistic toggle through `PUT /bff/stars`, rollback + toast; `useStars()`'s inert default | No change. Do not read the flag here: keeping the store flag-agnostic is what leaves the Studio gallery and unit renders unchanged |
| `frontend/src/locales/de/components.ts:29-41` | Two comment lines explaining the "markieren" choice, then **ten** star keys at `:31-41` | Unchanged. Every `t()` call stays in source, so the coverage test still finds a static caller for each. Stars needs no new strings; the toggle-row label belongs to the flag chrome |
| `frontend/src/styles/tailwind.css:35-36,58` | `--animate-star-pop` and the keyframes | Unchanged. Unused custom properties cost nothing; deleting them is irreversible for a live toggle |
| `tests_e2e/` | No page object exposes a star selector; there is no star coverage anywhere | Nothing breaks, and nothing guards the flag. See the open question |

**Judgement calls.**

1. **Where to gate.** At call sites (recommended), with an optional after-hooks guard inside `star.tsx` as defence in depth. The reason is hook identity on a live flip, not a flex gap. Three call sites additionally must withhold the element for layout: `PaperHeaderFrame`'s `action` slot, `ReaderFrame`'s required `star` slot in the archive, and the ledger's whole star column (decision D2).
2. **`starredOnly`.** Derive the effective value (`features.stars && state`) rather than deleting the state (recommended). Deleting it forces edits to the filter closures, memo deps, `filterKey`, `filtersActive` and `resetFilters` in three components.
3. **`StarsProvider`.** Keep it mounted with `emptyStars` (recommended) rather than dropping the element. Identical behaviour, smaller diff, and no future consumer trips over a missing provider.
4. **Skeleton flags.** One `features: Features` prop (§3.4), never a cookie read inside a skeleton. `EditionBrowserSkeleton` and `BriefingLedgerSkeleton` are client components (`briefing-archive/edition-browser.tsx:1`, `briefing/briefing-ledger.tsx:1`) and could not read cookies anyway. It is **optional, defaulting to `ALL_ON`,** on the five components the Studio gallery renders directly (`PaperHeader`, `PaperHeaderSkeleton`, `PaperNav`/`PaperNavSkeleton`/`PaperNavFrame`, `EditionBrowserSkeleton` and, since #52, `BriefingLedgerSkeleton`) so those call sites compile unchanged, and **required** everywhere else so a missed call site is a typecheck failure rather than a silent all-on render.
5. **Reserved gutters** (`pr-8`, `pr-9`). Leave them. Invisible, shared with the skeletons, and removing them is churn outside the flag's blast radius.
6. **`rs-stars` on flag-off.** Do not clear it. That is what makes flipping back on restore the same stars.

**Open questions for the product owner.**

- With nothing starred, the flip is clearly visible on `/papers/[id]` and `/briefing/[date]` (the labelled toggles), on the four Starred chips, and on `/briefing`, where the ledger loses a column; the card and rail stars are invisible until hover on a laptop, though not on a touch device (`star.tsx:68`). Is that enough of a change to demo, or should the demo browser have a few papers starred first?
- Settled 7 Sep 2026: star state survives invisibly while the feature is off (the `rs-stars` cookie is kept), so flipping back on restores the same stars.
- Turning stars back **on** re-engages any Starred filter the browser still holds: `/papers` and the archive re-narrow, with the chip reappearing already active, and on `/briefing` a `?starred=1` still sitting in the URL re-narrows the ledger too. Intended, or should a flip reset the filters?
- Do you want a Playwright spec for this flag? There is no star coverage in `tests_e2e/` today, so nothing guards it either way, and the spec must ship as its own PR.

### 4.3 `ask`

**Semantics.** The analyst can neither reach nor see the corpus-wide chat canvas. The nav loses its Ask row, in the rail and the drawer together. `GET /ask` and every query-string form of it (`/ask?paper=<id>&session=<id>&q=<question>`) render the shell's not-found card, streamed inside an **HTTP 200**, not a 404 status, because `/ask` has a `loading.tsx`; this is the same shape as a dead paper permalink and is the trade already decided and pinned at `frontend/docs/skeletons.md:147-149`. The one in-app href to `/ask` outside the nav is the search panel's Ask row on Home: for a question-intent query `buildSections` puts an "Ask about “{title}”" row first (`frontend/src/components/corpus-search/rows.ts:60-75`, rendered at `panel.tsx:119`), pointing at the `askHref()` built in `frontend/src/lib/bff/search/assemble.ts:26-28`. That row is not rendered when `ask` is off. **The "Ask this paper" sidecar stays**: the product owner decided (7 Sep 2026) that this flag hides the corpus-wide canvas and its entry points, not the per-paper assistant, so the pill, its sheet and its labels at `frontend/src/app/(sidebar)/papers/[id]/paper-chat.tsx:25-31,32,126-127` are untouched (see judgement call 1). Since #53 there is nothing there to gate in any case: the sidecar's old "Continue on Ask" link was already deleted upstream, so **PR 4 touches paper detail nowhere** (decision D3). Nothing else links to `/ask`: there is no Ask CTA on briefings or the papers list, and no command palette or global hotkey anywhere in the app. The Ask canvas never writes its paper, session or question back to the URL, so `/ask?paper=&session=&q=` stays a read-only inbound contract, with the nav's plain `/ask` and the search panel's Ask row as its two in-app producers. "Removed, not disabled" is about rendering: no file under `src/app/(sidebar)/ask/` may be deleted, because the Studio gallery imports `HistorySidecar`, `PaperPicker` and `PaletteEntry` from that folder, and `src/locales/de/ask.ts` must stay so the flag is reversible mid-demo. The chat BFF stays live under either scope option, because the cookie is a per-browser preference the visitor owns, because Django's `/api/chat/*` is reachable through the proxy rewrite regardless, and because the stream route is the one surface where a mid-response behaviour change is unrecoverable. `GET /bff/papers/palette` (`frontend/src/app/bff/papers/palette/route.ts:12`) belongs in that same list: since #66 the picker's corpus is a client-side fetch to its own route, not a server read inside `sections.tsx`, and it stays live too. There is one cross-flag consequence to keep in view: `all_papers` off removes the Ask row as a **side effect**, because the whole search panel goes with it (decision D1), while `ask` off with `all_papers` on must gate that row **explicitly** through `features` on `RowContext` (`corpus-search/rows.ts:34-40`; `CorpusSearch` is `'use client'`, so `useFeatures()` reads it directly). `AnswerMarkdown` is emphatically **not** an Ask component: it renders briefing briefs, Home's masthead, the ledger and paper rationales. Neither are `src/lib/chat/*`, `src/lib/sse/*` or `src/lib/bff/chat/*`, all shared with the paper sidecar and the gallery fixtures. One affordance survives by construction and should be said out loud: a switch labelled "Ask" remains in the account menu, including the Studio one, which is how the feature comes back.

**Touchpoints** (sorted by file).

| file:lines | what | when off |
|---|---|---|
| `.claude/skills/screenshots/SKILL.md:16,55,112` | The screenshots skill's route list, the `--routes` subset names (incl. `nav-open`, `ask`), and the replay note | No change (outside `frontend/`). `:55` is the operative line for a flag-off pass, and it is already stale (still lists `scoring`, removed 2026-09-01) |
| `REQUIREMENTS.md:58-67` | FR-6, "Interactive Paper Chat & Scientific Reasoning Engine (`/ask`)" | No change. Say in the PR that the flag is a demo affordance in one browser, not a withdrawal of FR-6 |
| `docs/error-ux/deferred-items.html:222-233,258-263` | Deferred item D01: split `/ask`'s coarse `Promise.all` so a failing rail cannot remove the composer | No change, but anchor the gate to the **top of the function body**, not "above the Promise.all", so D01 can land later without moving the flag check below an await |
| `docs/frontend-handover.md:148-156` | The second post-deploy smoke-check block: "a question in Ask streams" | Add the clause: the smoke check assumes the default browser state (no `rs-features` cookie). Otherwise an operator who ran a demo reads a healthy deploy as broken |
| `docs/user_journeys/personas.md:16,63,95,137` | Persona matrices marking the Ask console visible per role | No change (outside `frontend/`). Name the distinction in the PR: this flag is per browser, not per role |
| `docs/user_journeys/route_matrix.md:30,52,55,65,66,80` | The `/ask` row, the `run_id`/`paper_id` param rows, the briefing CTAs | No change. Already drifted: the shipped param is `?paper=` |
| `docs/user_journeys/user_journeys.md:41,238,309,518,531` | The Ask console journey and its CTAs | No change |
| `docs/user_journeys/wireframes.md:24,30,205` | Both personas' nav wireframes list "Ask Paper (/ask)"; section 5 is the console wireframe | No change. Lines 24/30 are the only other place the nav row is enumerated |
| `frontend/CHANGELOG.md:3-10` | The "2026-09-01 (Scoring page removed)" entry: nav entry, German dictionary and Playwright journey deleted, URL 404s, BFF kept on purpose | Add a dated entry in that voice, and name where this work **departs** from that precedent: dictionaries and journeys are kept, because the flag is reversible |
| `frontend/README.md:17,80,181` | "Ask streams the backend's chat"; the `ask/` tree entry; the snapshot-serve note | No change to any of the three. Listed so the README edit is not mistaken for the file's only Ask reference |
| `frontend/README.md:46-49,51-52` | The Ask feature bullet and the bilingual-UI bullet | Add the flag note beside the bilingual bullet (see the `all_papers` table) and a clause on the Ask bullet: hidden per browser, nav row gone, the route shows the not-found card |
| `frontend/docs/backend-swap-notes.md:29,193` | Historical swap notes listing `/ask` | No change; a dated record |
| `frontend/docs/backend-swap-plan.md:17,77` | The swap slices, and the note that `paper-chat.tsx` stays simulated "for the Ask slice" | No change. `:77` is the historical record of why the sidecar and the canvas were built as one slice; the flag now splits them on purpose, so the note stays as history |
| `frontend/docs/deploy-handoff.md:55` | The post-deploy smoke test: "a question in Ask should stream" | Same clause as `docs/frontend-handover.md:155` |
| `frontend/docs/skeletons.md:137,143` | The paper-detail paragraph naming "the chat pill" and `PaperChatFrame`/`PaperChatSkeleton` | No change: the pill and its skeleton are unconditional under the settled scope. Only the `/ask` section at `:151-159` gains a sentence |
| `frontend/docs/skeletons.md:147-149` | The decided trade: a `notFound()` under a `loading.tsx` answers HTTP 200 with the not-found page in-stream, pinned by `skeleton:drift --not-found` | No edit, but this is the paragraph the design must agree with. The `/ask` doc note must say the flag-off route behaves exactly like a dead paper permalink |
| `frontend/docs/skeletons.md:151-159` | The `/ask` section: one boundary, `HistorySidecarSkeleton`/`PaperPickerSkeleton` for the gallery | Add one sentence: flag-off, the route renders the not-found card before its Suspense boundary resolves, and the gallery panels stay regardless. While editing, note that `:151-152` ("the corpus feeds the picker, the sessions feed the recent-chats sidecar; both block it") went stale with #66 and not with this work: neither fetch is server-side any more |
| `frontend/docs/skeletons.md:187-190` | "Refs and motion stay in the client file. ask.tsx keeps bodyRef…" | No change. Named so the doc edit is scoped: `skeletons.md` has three Ask passages and only two can go stale |
| `frontend/scripts/lib/browser.ts:59-65` | `newContext()` seeds `rs-lang` by hand at `:64`; `lang` is a field on `BrowserOptions` at `:17` | No change now. A flag-off review pass needs a `--features` option here **and** parsed separately in each script (see the two rows below) |
| `frontend/scripts/screenshots.ts:97-98,128,152,178-193,212` | The `--lang` option (declared, validated, documented), the `nav-open` pseudo-route, and `{ name: 'ask', route: '/ask', auth: true }` at `:212` | No change. The sweep runs cookieless, so `/ask` still shoots. `nav-open` is the frame that proves the drawer lost the row. A flag-off pass must still exclude the `search-open` pseudo-route (`:194-206`) whenever `all_papers` is the flag being turned off, since that shot hangs without the field |
| `frontend/scripts/skeleton-drift.ts:59,70-98,234-257` | `parseArgs` has no `--lang` case and hardcodes `lang: null` at `:59`; `checkNotFound()` asserts `status === 200 && copy` | No change to ship the flag, but correct the verification story: `bun run skeleton:drift --not-found /ask` **cannot** seed a cookie today. That option has to be added here as well as in `browser.ts` |
| `frontend/src/app/(sidebar)/ask/ask.tsx` | The canvas: composer, tool menu, paper chip, transcript, sidecar, session CRUD | No change, not deleted. Note the real constraint: nothing outside the folder imports `ask.tsx`. The external-importer lock covers only `history-sidecar.tsx`, `paper-picker.tsx` and `types.ts`; everything else stays because the flag is reversible |
| `frontend/src/app/(sidebar)/ask/console-frame.tsx` | Shared canvas chrome, used by `ask.tsx` and `skeletons.tsx` | No change |
| `frontend/src/app/(sidebar)/ask/error.tsx:6-23` | Route error boundary | No change; unreachable, since `notFound()` renders the not-found page, not this |
| `frontend/src/app/(sidebar)/ask/history-sidecar.tsx` | The recents sidecar plus `HistorySidecarSkeleton` | No change, and it must keep exporting: `studio/skeletons/gallery-clients.tsx:4` and `page.tsx:19` import it |
| `frontend/src/app/(sidebar)/ask/loading.tsx:9-11` | Renders `AskPageSkeleton`; Next paints it before the page function runs | `const { ask } = await getFeatures(); if (!ask) return null`. The file must stay: deleting it turns `loading-convention.test.ts:35` red. Returning null keeps the glob satisfied and stops the Ask skeleton being the first painted body of a hidden route |
| `frontend/src/app/(sidebar)/ask/page.tsx:10,12-15` | `dynamic = 'force-dynamic'`; `generateMetadata` returns `{ title: t('Ask the scanner') }` | Gate `generateMetadata` too (`return {}`), or the hidden route advertises itself in the tab. The title then falls back to the root default "Research Intelligence". No cached variant to worry about |
| `frontend/src/app/(sidebar)/ask/page.tsx:26-61` | `AskPage` awaits `getT()`, `getWorkspacesState()` and `searchParams` in one `Promise.all` (`:31-35`), then either the workspace-notice branch (`:37-44`) or the canvas; the params type is `{ paper?, session?, q? }` at `:29` and `q` is handed on at `:57` | `await requireFeature('ask')` as the first statement. The reason to put it first is that it skips `getWorkspacesState()`, a Django round-trip. It is **not** about the corpus and session reads: since #66 those are client-side effects (`ask/use-palette.ts:35` and the history effect in `ask.tsx`), which cannot run at all once the page 404s. Note the segment has three server paths; a reviewer checking "is Ask really gone" must not stop at the canvas |
| `frontend/src/app/(sidebar)/ask/paper-picker.tsx` | The attach-a-paper palette plus its skeleton | No change; imported by the gallery |
| `frontend/src/app/(sidebar)/ask/scanner-turn.tsx:111,145,172,218-224` | One Q+A turn: answer, citation cards, verdict | No change. The citation `href` comes from the stream frame; see the `all_papers` table |
| `frontend/src/app/(sidebar)/ask/scanner-turn.test.tsx` | Unit test for the turn renderer | No change |
| `frontend/src/app/(sidebar)/ask/sections.tsx:14-38` | `AskSection` fetches **neither** the corpus nor the sessions since #66: one `papers.get(paper)` at `:25` resolves a `?paper=` deep link, `:29` trims `?q=` into `initialQuestion`, and `<Ask initialTarget initialSessionId initialQuestion/>` follows at `:32-37` | No change; never reached. Correcting the old claim matters for the gate's rationale, not for the gate: see the `page.tsx` row above |
| `frontend/src/app/(sidebar)/ask/skeletons.tsx:30-84` | `AskConsoleSkeleton` (Suspense fallback) and `AskPageSkeleton` (loading) | No change |
| `frontend/src/app/(sidebar)/ask/tool-menu.tsx:29-96` | The composer's "+" menu (`ToolMenu` declared `:29`); only Attach a paper is wired, the rest sit under `t('Not yet available')` at `:86` | No change. The attach flow lives inside the canvas, not outside it |
| `frontend/src/app/(sidebar)/ask/types.ts:6,9` | Presentation types; `PaletteEntry` is now a re-export of the papers contract's slim projection from `@/lib/bff/papers/schema` | No change, and it stays the gallery's import surface: `studio/skeletons/gallery-clients.tsx:6` imports the type from here, not from the schema |
| `frontend/src/app/(sidebar)/ask/use-transcript-scroll.ts` | Scroll/anchor hook | No change |
| `frontend/src/app/(sidebar)/layout.tsx:21-25` | The seeding point | Add `getFeatures()` to the `Promise.all` and pass `features` (see §3.4) |
| `frontend/src/app/(sidebar)/not-found.tsx:21-32` | Two hardcoded CTAs: `/papers` and `/briefing` | Flag-filter the CTAs (server component, `await getFeatures()`), falling back to `/dashboard`. No `ask`-specific code, but `ask` off is what makes this page a routine demo surface, so it must not chain into a second 404 |
| `frontend/src/app/not-found.tsx:28,34,37` | The root 404 (#50), outside the shell: `/dashboard` at `:28` and `/papers` at `:34-37` | Same filter, same PR 1 (decision D4). It matters more for `ask` than the CTAs suggest: this is the page with **no account menu**, so a visitor who lands here cannot flip the flag back on and must reach `/dashboard` first |
| `frontend/src/app/(sidebar)/papers/[id]/loading.tsx:9-11` | Renders `PaperPageSkeleton`, which wraps `PaperRecordSkeleton` and its `PaperChatSkeleton` | No change. The pill stays with `ask` off, so its skeleton keeps reserving the same space; `PaperChatSkeleton` passes no `link`, so it already matches the loaded frame with the link withheld |
| `frontend/src/app/(sidebar)/papers/[id]/paper-chat.tsx:25-31,32,126-127` | The "Ask this paper" sidecar: the doc comment (`:25-31`), `PaperChat` itself (`:32`), and the `t('Ask about {title}')` / `t('Ask this paper')` label and title at `:126-127` | **No change, and no guard either.** The sidecar stays with `ask` off (product owner decision, judgement call 1), and the old "Continue on Ask" link that would have been PR 4's one paper-detail edit was deleted upstream in `45ac032` (PR #53): `PaperChatFrame`'s props (`:232-252`) have no `link` slot any more. `sections.tsx:102` and `skeletons.tsx:64` are untouched, so the pill and its bone keep rendering together |
| `frontend/src/app/(sidebar)/papers/[id]/sections.tsx:54,101-102` | Server section renders `<PaperChat paper={paper}/>` at `:102` | `{features.ask && <PaperChat paper={paper}/>}`, reading the `features` object already on `PaperRecord`'s signature (`:54`, added in PR 2). No new prop, no `getFeatures()` call here |
| `frontend/src/app/(sidebar)/papers/[id]/skeletons.tsx:23,64,71,81` | `PaperChatSkeleton` at `:64`, inside `PaperRecordSkeleton` (`:23`), which `PaperPageSkeleton` (`:71`) renders at `:81` | `{features.ask && <PaperChatSkeleton …/>}`, using the `features` prop PR 2 put on both signatures. Supplied at `page.tsx:33` → `:55` and by `loading.tsx:10`. Nothing new to thread |
| `frontend/src/app/bff/chat/README.md` | Purpose and the BFF route table | One line recording the decision: the chat routes are not flag-gated. Writing it here is what stops the next reviewer "fixing" it |
| `frontend/src/app/bff/chat/sessions/route.ts:8-9` | `GET /bff/chat/sessions` | No change; stays live |
| `frontend/src/app/bff/chat/sessions/[id]/route.ts:9-26` | GET/DELETE/PATCH one session | No change; stays live |
| `frontend/src/app/bff/chat/stream/route.ts:21-86,92-110` | `POST /bff/chat/stream` (`:21-86`); `resolveScope()` (`:92-110`) builds a `/papers/{id}` citation at `:107`, behind the `if (!body.paper_id)` early return at `:96` | No change, under both options. Say so in the PR so it does not read as an omission |
| `frontend/src/app/bff/papers/README.md:8` | Names "the Ask paper palette" among the papers resource's consumers | No change. It is the doc that answers the cross-flag question from the BFF's side: the palette is a first-class consumer, independent of the `/papers` page |
| `frontend/src/app/bff/papers/palette/route.ts:12` | `GET /bff/papers/palette`, the picker's corpus since #66, fetched from the client by `ask/use-palette.ts:35` after the canvas paints | No change, stays live. It is Ask's own data path and is not gated: the same preference-versus-authorization reasoning as the chat routes |
| `frontend/src/app/loading-convention.test.ts:13-18,24-35` | Every force-dynamic page needs a sibling `loading.tsx` or listed debt; the list may only shrink | No change. This is what forecloses "delete `ask/loading.tsx` to get a hard 404": it turns `bun test` red, and adding `ask/page.tsx` to `KNOWN_UNCOVERED` is a deliberate ratchet reversal |
| `frontend/src/app/studio/layout.tsx` | The Studio shell | Must call `getFeatures()` and pass it. The three toggles appear in the Studio account menu because `AccountDropdownMenu` is shared chrome; a defaulted prop would render them in the wrong position |
| `frontend/src/app/studio/skeletons/gallery-clients.tsx:1-31` | `HistorySidecarDemo` and `PaperPickerDemo`, importing from `../../(sidebar)/ask/` at `:4,5,6` | No change. This is why "hidden means deleted" must not be taken literally for the `ask/` folder |
| `frontend/src/app/studio/skeletons/page.tsx:19-21,492-508,510-524` | The two "Ask ·" gallery pairs, `history-sidecar` (`:492-508`) and `paper-picker` (`:510-524`), fed by `fixtureSessions` and `PaletteEntry` | No change: `/studio` is the operator surface, its subtree is pinned all-on (§3.4), and the gallery is where drift is caught. Neither pair has a `PaperChat` counterpart, and PR 4 touches paper detail nowhere, so the pill is not a gallery or `skeleton:drift` concern either way |
| `frontend/src/components/answer-markdown.tsx` | `AnswerMarkdown` + skeleton | **No change, and not an Ask component.** It renders briefing briefs, the Home masthead, the ledger, paper rationales and the gallery. Hiding it would gut three other pages |
| `frontend/src/components/application-layout.tsx:48-54,58-64` | `ShellNavItem`; `coreNav`'s `/ask` row at `:62` | Add `feature?: FeatureKey`; tag the row `feature: 'ask'` |
| `frontend/src/components/application-layout.tsx:84-140,206-216,268-287` | `AccountDropdownMenu`, mounted twice (navbar and sidebar footer), both behind the `mounted` guard | Where the toggle rows go. Two consequences: the menu grows and must still fit anchored `top start`; and it renders only after hydration, so no server-rendered fallback carries the switches |
| `frontend/src/components/application-layout.tsx:166-172` | `ApplicationLayout` wraps `LanguageProvider` | Wrap `FeaturesProvider` the same way, taking `features` beside `lang` |
| `frontend/src/components/application-layout.tsx:251-260` | `nav.map(...)`, with the prefix-highlight expression at `:255` | The single filter site; removes the row and its `startsWith('/ask')` highlight |
| `frontend/src/components/corpus-search/rows.ts:34-40,60-75,181-182,194,207` | `askSection()` builds the "Ask about “{title}”" row from `result.ask.href` (`:60-75`); it is pushed after an exact-id hit (`:181-182`) and ordered **first** for a question-intent query (`:194`, `:207`). `RowContext` (`:34-40`) is the object `buildSections` already threads | **The one in-app `/ask` href outside the nav.** Add `features` to `RowContext` and return `null` from `askSection` when `ask` is off. `CorpusSearch` is `'use client'`, so `useFeatures()` supplies it at the top and no prop crosses a server boundary |
| `frontend/src/components/corpus-search/panel.tsx:119` | The panel's `case 'ask'` renders the row's label and arrow | No change: with no Ask row in `sections`, the branch never runs. Do not gate here as well, or the two gates can disagree |
| `frontend/src/lib/bff/search/assemble.ts:26-28` | `askHref(question, paperId)` builds `/ask?q=…&paper=…` on the server, inside the search response | No change. The BFF may keep offering the href; the UI decides whether to render a row for it. Gating here would put a per-browser preference inside a shared server response |
| `frontend/src/locales/de/components.ts:31` | `'Ask about “{title}”'` → `'Zu „{title}“ fragen'` | Keep. The rule is "keep every existing key, drop callers freely": the row becomes conditional, the string is not deleted |
| `frontend/src/components/sidebar-layout.tsx:64,68` | `{sidebar}` rendered twice from one node: desktop rail and mobile drawer | No change, and the proof that filtering the `nav` array covers both |
| `frontend/src/lib/auth/safe-next.test.ts:6` | `safeNext('/ask?x=1')` as a sample same-origin path | No change. A post-login `?next=/ask` with the flag off lands on the not-found card, which is the decided behaviour |
| `frontend/src/lib/bff/chat/contract.ts:97,109,120` | Declares `/bff/chat/stream`, `/bff/chat/sessions`, `/bff/chat/sessions/{session_id}` | No change. The flag never changes what the BFF offers |
| `frontend/src/lib/bff/chat/fixtures.ts` | `fixtureSessions` and `fixtureStreamFrames` for `BFF_SOURCE_CHAT=stub` | No change: `studio/skeletons/page.tsx:13` imports `fixtureSessions`, so this stays live with Ask hidden |
| `frontend/src/lib/bff/chat/reframe.ts`, `upstream.ts`, `schema.ts`, `service.ts` | The chat seam: SSE re-framing, Django row shapes, zod contract, `listSessions`/`getSession`/`deleteSession`/`renameSession` | No change; shared with the paper sidecar and the gallery fixtures |
| `frontend/src/lib/bff/core/source.ts:23,53` | The `chat` resource (`BFF_SOURCE_CHAT`, default `django`) | No change. Sourcing is a deploy concern; `BFF_SOURCE_CHAT=stub` still serves Ask, just from fixtures |
| `frontend/src/lib/bff/papers/service.ts:125` | `listEverywhere()`. It is **not** Ask's corpus read any more: since #66 the picker fetches `GET /bff/papers/palette` from the client (`ask/use-palette.ts:35`, fired from `ask.tsx:127` after paint), and that route calls `recentCorpus()`, not this | No change. Still listed because Ask's data path runs through the papers resource, not only through `bff/chat/*`; only the entry point moved |
| `frontend/src/lib/chat/*`, `frontend/src/lib/sse/*` | `use-chat-stream`, `consume-stream`, `citation-markers`, `use-smooth-text`, the SSE parser and writer, and their unit tests | No change. All shared with the paper sidecar, `answer-markdown.tsx` or the stream route |
| `frontend/src/locales/de/ask.ts:1-106` | Every Ask chrome string | No change. The page is removed, not deleted; the dictionary must survive for the flag to be reversible |
| `frontend/src/locales/de/chrome.ts:9,37` | `'nav\|Ask': 'Fragen'` and `"Couldn't load Ask."` | Both stay. `t('Ask', 'nav')` is the toggle-row label and needs **zero** new keys: `frontend/src/lib/i18n.ts:20` resolves the context key first, and `de/ask.ts:8` records the shipped decision that the nav's "Ask" translates through this context. Only a group heading ("Demo features") needs a new key here |
| `frontend/src/locales/de/papers.ts` | The `'Continue on Ask'` key and the Ask-this-paper rail block that used to sit at `:134,138-148` | **Already gone**, deleted upstream by `45ac032` (PR #53) along with the link itself and two paper-chat history keys. Nothing to keep and nothing to drop; listed so a reviewer hunting for them knows why they are missing |
| `frontend/src/lib/i18n.test.ts:16,27,59` | The ask dictionary is an area; the file gate only scans files containing `useT()`/`getT()`/`makeT(`/`t?: `/`t: T` | Do not trim `de/ask.ts`. If any toggle copy ends up in a new module, that file must carry one of the gate tokens or its `t()` calls are never scanned |
| `frontend/src/proxy.ts:36-42,60-64,144-158` | The backend rewrite, the auth gate, and the `rs-lang` detect/forward dance | No change. Flags need no seeding, so this stays off the auth-refresh path |
| `frontend/contract/bff.openapi.json:206,487,601` | The generated artifact declaring the three chat paths | No change under the recommended decision. Listed because gating the routes would require regenerating it, and a stale artifact makes `contract-check.ts` disagree with the code |
| `docs/i18n/audit.html:116` | The shipped P1 finding: "The feature has three names in each language → One name (Ask / Fragen)" | No change. It settles the label question without going to the owner |
| `docs/i18n-backlog.md:98` | The backlog note about the Ask history aside | No change |
| `tests_e2e/README.md:15,23,79` | Describes `SidebarNav` traversing `/ask`, journey 05, and `specs/ask.spec.ts` | No change (outside `frontend/`). This is where the "the suite assumes every flag defaults ON" note belongs. `specs/ask.spec.ts` does not exist |
| `tests_e2e/run_frontend_e2e.sh:81-83` | The `ask\|--scenario=ask\|specs/ask.spec.ts` branch | No change. Already dead: it selects nothing. The real coverage is specs 05 and 06 |
| `tests_e2e/pages/AskPage.ts:11-98,25,44` | The Ask page object; `pageTitle` matches `h1:has-text('Ask'/'Fragen')`, `isPageLoaded()` waits on the composer | No change. Sharpen the note: flag-off, the URL still reads `/ask` and the not-found page has no `<h1>`, so a flag-off run fails on a 5-second visibility timeout rather than a clean assertion |
| `tests_e2e/pages/SidebarNav.ts:21,27-29,89-101,139-143` | `navAsk` (`:21`); the `['ask','chat','/ask']` branch of `navigateTo` with its `goto()` fallback; the three account-menu locators (`:27-29`) and `toggleLanguage()` | No change, but a hard constraint on the toggle rows (see §3.5): same `[role='menu'] [role='menuitem']` shape, no colliding label text |
| `tests_e2e/pages/WorkspaceSwitcher.ts:18-19,38-52` | `openDropdown()` returns true for **any** visible `[role='menu']`, then reads every menuitem as a workspace name | No change today (both callers run with no menu open). The account menu is read by two page objects, not one |
| `tests_e2e/specs/05_interactive_paper_chat.journey.spec.ts:13-30`, `06_end_to_end_researcher_flow.journey.spec.ts:8,17,43-45` | The two journeys that visit Ask | No change; they pass on defaults and are the regression net for the flag-on path |

**Judgement calls.**

1. **Scope on paper detail: the sidecar stays, and there is nothing left to gate. Decided by the product owner, 7 Sep 2026, then overtaken by #53.** The draft read the brief as "no assistant anywhere" and would have hidden the "Ask this paper" pill, its sheet and its skeleton with two `&&` guards at `sections.tsx:102` and `skeletons.tsx:64`. The owner chose the narrower reading: `ask` hides the corpus-wide canvas and every link into it, and the per-paper assistant is a separate feature that keeps working. The draft still kept one paper-detail edit, the `link` slot carrying "Continue on Ask". That link is gone from the codebase: `45ac032` (PR #53) deleted the `<Link>`, its `continueHref`, the `link` slot on `PaperChatFrame` (whose props are now `paper-chat.tsx:232-252`) and the German keys. Consequences (decision D3): **PR 4 touches paper detail in no place at all**; the sidecar documented as "deliberately bare, history browsing lives on Ask" (`paper-chat.tsx:25-31`) already lost its escape hatch upstream, which is accepted; the one `/ask` link that does need a guard is the search panel's Ask row in `corpus-search/rows.ts`; and if the wider reading is ever wanted, it is still those two `&&` guards, reading the `features` prop PR 2 already threads, with no new signatures.
2. **HTTP status.** Accept the 200-in-stream for `/ask` (recommended). The alternatives are deleting `ask/loading.tsx` (fails `loading-convention.test.ts`, loses the skeleton) or gating in the proxy (contradicts the no-proxy decision).
3. **`loading.tsx`.** Gate it to `return null` (recommended) rather than letting the Ask skeleton paint under the hidden route. One extra cookie read on a route that is already force-dynamic and hidden.
4. **Chat BFF routes.** Stay live. The reasoning is preference-versus-authorization plus not touching the streaming hot path before a demo, and it does not depend on what happens on paper detail. There is no "gate them if the sidecar goes" fallback.
5. **The Studio gallery's two "Ask ·" pairs.** Leave them (recommended). Filtering them would tie drift coverage to a demo cookie.

**Open questions for the product owner.**

- Do you ever show `/studio` during the demo? The two "Ask ·" gallery panels stay visible with the flag off.
- Settled 7 Sep 2026: the per-paper "Ask this paper" pill stays with `ask` off; only the corpus canvas and its links go (judgement call 1). The only such link left in the app is Home's search-panel Ask row, since paper detail's was deleted upstream (decision D3), and that row also disappears whenever `all_papers` is off, because the whole panel does.
- The menu needs a group heading above the three switches. "Demo features" is the working English; we need the German too. It is one of only two new dictionary strings this work adds (the other is `Stars: 'Markierungen'`); everything else reuses shipped copy.

---

## 5. Cross-cutting

**i18n.** New German strings go in `frontend/src/locales/de/chrome.ts`, beside `Sign out`, not in a new `de/features.ts`. That keeps `AREAS` (`frontend/src/lib/i18n.test.ts:27`) untouched, a hand-maintained list that is already out of sync, since `de/tuning.ts` is spread into `de/index.ts` but absent from `AREAS`, so a new module added to only one list inherits the same silent half-coverage. Two of the three row labels reuse existing German and one does not. `t('Ask', 'nav')` resolves through `chrome.ts:9` (`Fragen`). `All papers` already exists as `Alle Papers` in `de/papers.ts:77` and `de/ask.ts:53` and the merged dictionary finds it, so add no `chrome.ts` copy, and if one is ever added it must carry that exact string, or the duplicate-conflict test (`i18n.test.ts:85-96`) fails. **`Stars` has no German at all**: `de/components.ts:32` holds `Starred: 'Markiert'`, and grepping `src/locales/de/` finds no `Stars` and no `Markierungen`. So **two keys are genuinely new**, both in `de/chrome.ts` beside the nav keys: the section heading `'Demo features'`, and `Stars: 'Markierungen'` (following the deliberate "markieren, not Stern" choice recorded at `de/components.ts:29-30`). The alternative with one new key is to set `FEATURES.stars.label = 'Starred'` and reuse `de/components.ts:32`; either is fine, but leaving the label as a bare English `Stars` is not: the German menu would render an untranslated row and the registry-coverage assertion in `features.test.ts` (§3.8) would fail on its first run. Two traps: `i18n.test.ts:59` skips any file that does not contain `useT()`/`getT()`/`makeT(`/`t?: `/`t: T`, so a new component rendering a label must carry one of those tokens; and `i18n.test.ts:52-53` matches only string literals, so a registry-driven `t(def.label, def.ctx)` is invisible to the scanner and needs the explicit registry assertion in `features.test.ts` (§3.8).

**Tests.** `bun run check` = `format:check && typecheck && lint && bun test && scope:check`. Everything in this design lives under `frontend/` except the e2e spec, the `tests_e2e/README.md` note and this document, so gate each PR with `bun run check` and split the rest. `frontend/src/app/error-copy-convention.test.ts` globs every new `.tsx` under `src/app` and `src/components`, so any new flag component that surfaces a failure must route through `problemMessage()`, low risk, since the cookie write makes no server call. `frontend/src/app/loading-convention.test.ts` fires if a new force-dynamic page is added without a `loading.tsx`, and it is what forbids deleting `ask/loading.tsx`.

**E2E.** The suite is unaffected by construction: `tests_e2e/playwright.config.ts` targets the local dev server by default (prod was the default until PR #106), every context starts cookieless, and flags default ON. Two false-green hazards to record rather than fix: `SidebarNav.navigateTo` falls back to `goto(path)` when a nav link is missing, and `PapersPage.isLoaded()` returns true on the not-found card because it renders inside the shell's `<main>` (`frontend/src/components/sidebar-layout.tsx:82`). So a flag-off run of journeys 02 and 06 passes while every papers step is silently a 404, and a flag-off Ask run fails on a locator timeout rather than an assertion. Any flag coverage must assert **absence** with raw locators. `BasePage` has `getCookie` but no setter; a flag spec needs `context.addCookies([{ name: 'rs-features', value, url: baseURL }])`, the shape `frontend/scripts/lib/browser.ts:63-65` already uses for `rs-lang`.

**Screenshots and drift.** Both harnesses log in with a fresh cookieless context, so both see the full product and neither needs changing to ship the flags. To capture a flag-off before/after pair, a `--features` option must be added to `BrowserOptions` in `frontend/scripts/lib/browser.ts` **and parsed separately** in each script: `screenshots.ts` declares and validates `--lang` at `:97-98,128,152`, and `skeleton-drift.ts` has no such option at all and hardcodes `lang: null` at `:59`. Do not add flag-off variants to `SCREENS`: filenames are `SCREENS.indexOf(screen)+1` (`screenshots.ts:351`), so inserting renumbers everything after and breaks comparison with `docs/i18n/shots/*/manifest.json`; capture a separate `--out` run. Include the `nav-open` pseudo-route (`:178-193`) in any flag-off pair: it is the only frame that proves the nav filter reached the mobile drawer. **Exclude the `search-open` pseudo-route** (`:194-206`, registered at `:223-226`) from any run with `all_papers` off: it types into Home's combobox and waits for the listbox, so with the field hidden it hangs to its timeout and then fails the whole sweep (`:415`). A flag-off run must therefore name its routes explicitly with `--routes`. And note that a flag-off `/papers` shot fails the run loudly (HTTP ≥ 400 sets `failed = true`, `:408-412`) while `paper-detail` degrades to a logged skip, because `discover()` scrapes the id from `/papers` (`:278`).

**Snapshot replay.** Flags do not interact with it at all: the cookie is written by `document.cookie` and read by `next/headers`, and never crosses the seam to :8010. Two second-order notes for anyone capturing evidence on the replay: the `stars` resource defaults to the `stub` source, a browser cookie, so stars work there; and the documented pagination limit means `/bff/chat/sessions` is always empty, so an Ask before/after pair on the replay shows an empty sidecar in both frames, which is replay behaviour, not the flag.

**Docs.** `frontend/README.md` gets the flag bullet beside the bilingual one, plus `src/lib/features*.ts` in the project-layout tree. `frontend/CHANGELOG.md` gets a dated entry in the voice of the "Scoring page removed" entry, naming the deliberate difference: dictionaries and Playwright journeys are kept here, because the flag is reversible. `frontend/docs/conventions.md` gets the convention section once. `frontend/docs/skeletons.md` gets the flag-aware bone rule (`:177-179`), the `/ask` note (`:151-159`), the `--stream /papers` caveat (`:79-82`, `:221-224`) and the paper-detail paragraph (`:135-140`). `frontend/src/app/bff/README.md` gets one disambiguating sentence: `BFF_SOURCE_*` is a build/env data-source switch; feature flags are a per-browser UI cookie with no env or deploy involvement. Without it, "the flags" is ambiguous in this repo. `frontend/src/app/bff/chat/README.md`, `bff/papers/README.md` and `bff/stars/README.md` each get one line recording that the UI consumer is flagged and the route is not. Both post-deploy smoke checklists (`frontend/docs/deploy-handoff.md:55`, `docs/frontend-handover.md:148-156`) get a clause: the check assumes the default browser state. Leave `docs/user_journeys/*`, `REQUIREMENTS.md` and `docs/i18n/*` alone: they are outside `frontend/`, belong to other people, and describe role visibility or product requirements, not a per-browser demo toggle.

**Studio.** The gallery is pinned all-on by an explicit provider, not by accident. `studio/layout.tsx` passes the real `features` to `ApplicationLayout`, so the account menu's switches work from the operator surface too, and wraps its own children in `<FeaturesProvider features={ALL_ON}>` (§3.4). Nested context wins for the subtree, so `PaperCard`, `BriefingLedger` and `EditionBrowser`, which read `useFeatures()` and are rendered live in the gallery's loaded panes, keep their stars whatever the demo cookie says, while their skeletons keep their bones through the `ALL_ON` prop default. Four pairs show a star in their loaded pane and all four are covered: `paper-card` (`studio/skeletons/page.tsx:275`), `paper-header` (`:444`), `briefing-ledger` (`:531-535`) and `edition-browser` (`:549`). Both halves of every pair therefore agree, and `frontend/scripts/skeleton-drift.ts` measures the product rather than a cookie, which matters because that check runs signed in and would otherwise fail its 4px desktop gate on `paper-header`, `briefing-ledger` and `edition-browser` for anyone who opened `/studio` mid-demo. It stays green today only because the drift run is cookieless; the provider is what makes the invariant true instead of merely unobserved. Two consequences to keep: the `useFeatures()` context default is all-on, and the skeleton props default to `ALL_ON`. The gallery is keyed by component shape rather than by route and `skeleton-drift` fails outright if it finds zero `[data-pair]` sections, so filtering pairs by flag remains an explicit non-goal.

**Proxy and logout.** No proxy change and no matcher change. `replaceCookie` (`frontend/src/proxy.ts:208-214`) preserves every cookie it is not replacing, so `rs-features` rides through the token refresh untouched. The cookie is **not** added to `AUTH_COOKIES` (`frontend/src/lib/auth/cookies.ts:12`) and is not cleared by `clearAuthCookies` (`:77-80`) or by `auth/logout/route.ts:30`: like `rs-lang` and `rs-stars`, it survives sign-out, so the owner can set the demo state, sign out, sign in as the demo user, and find the flags where they left them. The app's cookie inventory after this work: `sri_access`, `sri_refresh`, `sri_user` (auth, httpOnly), `rs-lang` (preference, readable), `rs-stars` (stars stub store, httpOnly), `rs-features` (preference, readable).

**Hazards.**

- **Hydration.** No component may read `document.cookie` for flags; the value must arrive through the server-seeded provider. The account menu is already deferred to post-hydration by the `mounted` guard, but the **nav** is server-rendered, which is why it must be filtered from the seeded prop.
- **Memo identity.** `features` is a new object on every server render, and so is anything closing over it. Keying the context memo on the encoded string is only half the fix: `setFeature` must also be keyed on that string (with the pathname read from a ref), or the callback churns every render, drags the memo with it, and re-renders every star on the page on every refresh. §3.3 has the shape that actually holds.
- **The vanish guard.** Turning a flag off while standing on the route it owns must navigate away, and it must be **one hard navigation** (`window.location.assign('/dashboard')`), not `router.replace()` plus `router.refresh()` in the same tick: those two have no ordering guarantee, and the two failure modes are a 404 card flashing under the owner mid-demo or a client-router-cache render of `/dashboard` still showing the stale nav. `exact: true` on `/papers` keeps a flip on `/papers/<id>` from bouncing the reader off a page that is still valid. `stars` owns no route and always takes the plain-refresh path.
- **Two shells, one menu.** Both `(sidebar)/layout.tsx` and `studio/layout.tsx` must seed real flags, or Studio ships dead switches.
- **Per-browser is per-browser, and per-tab until refreshed.** A second laptop, a projector or an incognito window is unaffected; another tab already open keeps its rendered nav until it navigates. Say it in the PR so nobody debugs it live.
- **Turning flags back on is the untested half.** It is not derivable from the language toggle, which never hides the page it is standing on. Exercise the on direction in the running app before the demo: from `/dashboard`, flip each flag on and confirm the nav item returns.
- **`Secure`.** The language cookie omits it; mirror it exactly. Adding `;secure` on HTTPS is defensible, but then do it for both preferences in a separate change rather than leaving two cookies with different attributes.
- **Caching.** Nothing here opts into PPR or `cacheComponents`, and the `(sidebar)` layout is already dynamic because it reads cookies. If a page is ever made static, `requireFeature` is what fails the build, which is a useful tripwire.
- **`scope:check`.** `frontend/scripts/scope-check.ts:17` fails `bun run check` on any changed file outside `frontend/`. The e2e spec, the `tests_e2e/README.md` note and this document each need their own branch.

---

## 6. Implementation order

**PR 1: plumbing and the menu (all three flags wired, no feature hidden yet).**
`src/lib/features.ts`, `features-server.ts`, `features-client.tsx`; `ApplicationLayout` takes a required `features` and provides the context; `(sidebar)/layout.tsx` seeds it; `studio/layout.tsx` seeds it **and** wraps its children in `<FeaturesProvider features={ALL_ON}>`; the extended `@/components/dropdown` import, the two hook calls in `AccountDropdownMenu`, `StarIcon` added to the existing 20/solid import, `FEATURE_ICONS`, and the three toggle rows under a `Demo features` heading; `ShellNavItem.feature` added but no row tagged; the two new German keys in `de/chrome.ts` (`'Demo features'` and `Stars: 'Markierungen'`); `src/lib/features.test.ts`; the `/bff/status` field; the CTA filter on **both** not-found pages, `(sidebar)/not-found.tsx:21-32` and the root `src/app/not-found.tsx:34` (decision D4); the `bff/README.md` disambiguation sentence.
*Verify:* `bun run check` (the registry-i18n assertion in `features.test.ts` is what catches a missing German key). `bun run build`, and confirm no "used `cookies` inside a component that was statically rendered" warning for **either** not-found file, `(sidebar)/not-found.tsx` or the root `src/app/not-found.tsx`: a `cookies()` read inside a not-found boundary is the one place Next has historically tripped. In the browser: open the account menu from both the sidebar footer and the navbar, flip each switch, confirm the menu stays open across two flips, and confirm the menu still fits anchored `top start` on a laptop viewport. In devtools confirm the cookie reads `rs-features=all_papers.ask` with two flags off, and, with **all three back on**, that it reads `rs-features=` with an empty value, which is the correct all-on write, not a failure. Switch to German and confirm no untranslated row. `curl -s -o /dev/null -w '%{http_code}' <host>/papers` still returns 200 (nothing is gated yet). `bun run screenshots --routes dashboard,nav-open` for the before shot.
Note the deliberate half-state: on this branch alone, `all_papers` off removes the "Go to Papers" button from **both** 404 cards while `/papers` is still live and still in the nav. It lasts exactly one PR.

**PR 2: `all_papers`.**
Tag the nav row; `requireFeature` + `generateMetadata` gate on `papers/page.tsx`; Home's `<CorpusSearch>` typeahead and its skeleton (`dashboard/page.tsx:59` and `dashboard/skeletons.tsx:52`, decision D1: the whole panel goes, and Home's Ask row with it); the paper-detail crumb trail, the `PaperNav` back-link swap **in both the loaded row (`paper-nav.tsx:87-90`) and the skeleton (`:103-107`)**, the pager div withheld in `PaperNavFrame`, the `neighboursOf` skip; `papers/[id]/error.tsx`; `src/app/flagged-routes.test.ts`; the README, CHANGELOG and `skeletons.md` notes.
This PR introduces the `features: Features` prop of §3.4: **five signatures for `all_papers`, not two**: `PaperRecord` (`sections.tsx:54`, required), `PaperRecordSkeleton` and `PaperPageSkeleton` (`skeletons.tsx:23,71`, required), `PaperNav` / `PaperNavSkeleton` / `PaperNavFrame` (`paper-nav.tsx:82,99,28`, optional `= ALL_ON`), plus `DashboardSkeleton` (`dashboard/skeletons.tsx:48`, required), all supplied by `papers/[id]/page.tsx:33`, `papers/[id]/loading.tsx:10` and `dashboard/loading.tsx`. PRs 3 and 4 consume those props and add no signatures.
*Verify:* `bun run check` (typecheck is what proves the optional/required split: `studio/skeletons/page.tsx` must still compile untouched). Replay on :8010 (`bun run snapshot:serve`), then in the browser: **flip `all_papers` off from `/papers` itself** (the demo's most likely click, and the one path the language toggle never exercises) and confirm a single navigation to `/dashboard` with no 404 flash; then, after the page settles, assert the Papers row is gone from **both** the desktop rail and the mobile drawer (`bun run screenshots --routes nav-open`, `frontend/scripts/screenshots.ts:178-193`; name the routes explicitly, because a flag-off sweep must not include `search-open`, which hangs without the field). Paste `/papers` and confirm the not-found card with **no** "Go to Papers" button. `curl -s -o /dev/null -w '%{http_code}' -b 'rs-features=all_papers' <host>/papers` returns **404**. Open a paper from Home's TopPapers and confirm one working exit and no empty crumb bar; reload `/papers/<id>` and confirm the skeleton shows no crumb, no pager, and the same back label as the loaded row. Flip back on from `/dashboard` and confirm restoration. `bun run skeleton:drift` green.

**PR 3: `stars`.**
The layout seed skip; `paper-card.tsx` and the **four** `StarredChip` call sites (papers browser, briefings ledger, archive rail, edition paper list); the **four** `starredOnly` derivations, the ledger's being URL-derived (`const starred = features.stars && state.starred`, decision D2); `paper-header.tsx`'s `action` slot and `ReaderFrame`'s `star={… : null}` at `briefing-archive/edition-browser.tsx:312`; **the whole `/briefing` ledger**, which is new work since the first draft: the star column out of `COLUMNS` (`briefing-ledger.tsx:47`) together with its cell (`:128-132`), empty header label (`:75`, header row `:90-98`) and skeleton footprint (`:325-328`), and the `colSpan` at `:170` checked on a flag-off render; the ledger's `LedgerSkeletonRegion` and `BriefingPageSkeleton` (`briefing/skeletons.tsx:10,19`) and the archive's `EditionsSkeleton` and `BriefingPageSkeleton` (`briefing-archive/skeletons.tsx:7,16`); **all three** briefing-side `loading.tsx` reads (`briefing/loading.tsx:5-8`, `briefing-archive/loading.tsx:5-8`, `briefing/[date]/loading.tsx:8-11`); the briefing-date signature edit (`EditionHead` at `briefing/[date]/sections.tsx:29`); the star bones behind the `features` prop; the optional after-hooks guard in `star.tsx`; the `paper-card.test.tsx` sibling case; `bff/stars/README.md` and the `skeletons.md` bone rule. On the paper-detail side this PR only **consumes** the props PR 2 added.
*Verify:* `bun run check` (the new `paper-card.test.tsx` case is the regression guard). In the browser with a couple of papers starred: flip `stars` off and confirm the masthead toggles on `/papers/[id]` and `/briefing/[date]` disappear in the same commit as the chips, with no gap left in the paper masthead on a narrow viewport; engage the Starred chip on `/papers`, on `/briefing` (the ledger) and on `/briefing-archive`, then flip off, and confirm none of the three stays narrowed, that the ledger's table loses its star column cleanly rather than keeping an empty 28px gutter, and that the archive is not a dead end; reload `/briefing?starred=1` with stars off and confirm the **full** list, because that query survives in the URL by design (decision D2); flip back on and confirm the same stars return. `bun run skeleton:drift` green (the gallery must still show stars in all four starred pairs: `paper-card`, `paper-header`, `briefing-ledger`, `edition-browser`). Reload `/papers/[id]`, `/briefing` and `/briefing/[date]` and confirm no star bone flashes.

**PR 4: `ask`.**
Tag the nav row; `requireFeature` + `generateMetadata` gate on `ask/page.tsx`; the `ask/loading.tsx` null gate; the Ask row in `corpus-search/rows.ts` (`features` added to `RowContext` at `:34-40`, `askSection` at `:60-75` returning null), which is the only in-app `/ask` href outside the nav; **no paper-detail change at all** (decision D3: the sidecar stays by construction, and "Continue on Ask" was already deleted upstream in `45ac032`); `flagged-routes.test.ts` entry; the README, CHANGELOG, `skeletons.md` (the `/ask` section at `:151-159` only), `bff/chat/README.md` and the two smoke-check clauses.
*Verify:* `bun run check`. In the browser **flip `ask` off from `/ask` itself** and confirm a single navigation to `/dashboard` with no 404 flash; after the page settles, assert the Ask row is gone from **both** the desktop rail and the mobile drawer (`--routes nav-open`). Paste `/ask?paper=<id>` and then `/ask?q=x&paper=<id>` (the `?q=` form is inbound since #66) and confirm the not-found card, the tab reading "Research Intelligence", and **no Ask skeleton painting first**. `curl -s -o /dev/null -w '%{http_code}' -b 'rs-features=ask' <host>/ask` returns **200**, which is expected, and the reason is documented in §3.6. `curl -b 'rs-features=ask' <host>/bff/chat/sessions` and confirm it still answers, which is the decision. Type a question into Home's search and confirm the panel offers **no** Ask row for it; then open a paper and confirm the "Ask this paper" pill still works and the sidecar is untouched, which it is by construction. Flip back on from `/dashboard` and confirm the canvas, the nav row and the search panel's Ask row all return.

**PR 5 (separate branch, outside `frontend/`): e2e.**
`tests_e2e/specs/07_feature_flags.journey.spec.ts`, `tests_e2e/pages/FeatureToggles.ts`, the `addCookies` helper on `BasePage`, and the `tests_e2e/README.md` note that the suite assumes flags default ON.

---

## 7. Out of scope, and the door the registry keeps open

Not in this work: backend-owned flags (a Django-served flag set, per-user or per-tenant), per-domain flags (a feature on for one workspace and off for another), role-based visibility (that is what `docs/user_journeys/personas.md` describes and it is a different axis), any env, deploy or CI involvement, and any flag that gates a BFF route or acts as an authorization boundary.

The registry keeps those doors open cheaply. `FEATURES` is a `Record<FeatureKey, FeatureDef>` with a resolver, the same shape as `RESOURCES` in `frontend/src/lib/bff/core/source.ts:48-58`, so a `FeatureDef` can grow a field (a `source`, a `scope`, a per-domain override) without touching a single call site. Every consumer reads through `getFeatures()` on the server and `useFeatures()` on the client, so a future backend-served set changes exactly one function body: `getFeatures()` merges a server response over the cookie defaults, and nothing above it moves. The cookie's off-list encoding means a flag added later is on for every browser already carrying a value, and an unknown token is ignored, so no version field is needed. And because the flag is never read below the page layer (never in a service, never in the proxy, never in a BFF route), none of that plumbing has to be unpicked if the source of truth changes.

One thing deliberately not kept open: `BFF_SOURCE_*` stays a separate concept. Data sourcing is a build/env switch about which backend answers; feature flags are a per-browser UI preference. They should never be merged, and `frontend/src/app/bff/README.md` says so.
