# Deploy handoff — shipping this frontend on Cloud Foundry

The backend repo's `deploy.yml` builds `./frontend` and pushes `sri-frontend`
(Docker, bare root route). To ship this app instead of the Next 14
placeholder:

## 1. Get this repo into the image build

Either subtree `phase-2-core` into the backend repo's `frontend/`:

```bash
# in schwarz-research-intelligence/
git subtree add --prefix frontend <research-scanner-remote> phase-2-core --squash
# later updates:
git subtree pull --prefix frontend <research-scanner-remote> phase-2-core --squash
```

…or point the workflow's build context at this repo. The Dockerfile at this
repo's root is self-contained (`bun install` → `next build` standalone →
`node server.js`, honours CF's `PORT`); `deploy.yml`'s
`--build-arg BUILD_ID=<sha>` is already consumed.

## 2. `manifest.yml` changes for `sri-frontend`

```yaml
- name: sri-frontend
  memory: 512M # deliberate: the CF org quota is tight; 1G when it allows
  env:
    NODE_ENV: production
    BACKEND_INTERNAL_URL: https://<the shared hostname> # or the C2C internal route
    SITE_URL: https://<the shared hostname>
    # BFF sources — override as endpoints land (defaults in
    # src/lib/bff/core/source.ts):
    # BFF_SOURCE_PAPERS: composed
    # BFF_SOURCE_BRIEFINGS: composed
    # BFF_SOURCE_SCORING: composed
    # BFF_SOURCE_PREFERENCES: stub
    # BFF_SOURCE_STARS: django
    # Corpus snapshot bounds (defaults in src/lib/bff/corpus/snapshot.ts;
    # documented in .env.example). Keep CORPUS_CACHE_MAX_MB at or under 128
    # while the instance is 512M.
    # CORPUS_MAX_PAPERS: "2000"
    # CORPUS_CACHE_MAX_MB: "128"
    # CORPUS_PROBE_COOLDOWN_MS: "5000"
```

Notes:

- If `BACKEND_INTERNAL_URL` uses an internal route, its host must be in
  Django's `ALLOWED_HOSTS`.
- Cookies are `Secure` in production whenever `SITE_URL` is https (plain-
  http testing).
- The frontend proxies `/api /admin /static …` itself when Gorouter leaks
  them, so path routing stays as it is.

## 3. Smoke checks after deploy

```bash
curl -si https://<host>/                     # 200, login page
curl -si https://<host>/bff/papers           # 401 application/problem+json
# sign in in a browser, then /bff/status should list every resource,
# and a question in Ask should stream (watch for `: ping` comments).
curl -si https://<host>/health/              # Django, via the router
```

After the first sign-in, `cf logs sri-frontend --recent` should show no
`[bff] corpus capped` line; one means a user has more papers than
`CORPUS_MAX_PAPERS` and is seeing the newest of them. Past the cap: /papers
says so and shows the newest; a paper permalink and a single edition page
read what they need live; the briefing lists, Home's recent briefings and
the star list only see papers inside the cap, so an edition older than the
window lists no papers there (its counters, from the run, stay right).
Raise `CORPUS_MAX_PAPERS` before that happens for a real user.

These checks assume the **default browser state**: no `rs-features` cookie, so
every demo feature switch is on. A browser left over from a demo can have Ask
or Papers hidden, which reads as a broken deploy — clear the cookie, or turn
the switches back on from the account menu, before trusting the result.
`GET /bff/status` reports `features` for the calling browser.

`GET /bff/status` is the operational view: active source per resource and
whether each requested endpoint is present.
