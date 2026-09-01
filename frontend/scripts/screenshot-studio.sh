#!/usr/bin/env bash
# Capture the Studio screenshots with agent-browser, and optionally publish them
# to a pull request.
#
#   screenshots/studio/desktop/  — the Studio pages at a desktop viewport
#   screenshots/studio/mobile/   — the same pages at a phone viewport, where the
#                                  sidebar becomes a drawer and the step timeline
#                                  collapses to a single column
#
# Run ids are DISCOVERED from the runs list, not pinned: run ids differ between
# every snapshot, replay and environment, so a pinned id would break on the next
# `snapshot:pull`. The script shoots the newest run, and — separately — the
# newest run that closed early, because "halted" is the state worth reviewing
# and it is not always present in the first row.
#
# Usage:
#   scripts/screenshot-studio.sh [base-url]            # capture only
#   scripts/screenshot-studio.sh [base-url] --pr 9     # capture, then attach to PR #9
#
# Default base-url is the replay stack (see local-docs/snapshot-replay.md):
#   bun run snapshot:serve                                        # :8010
#   BUILD_DIR=.next-agent9 PORT=3009 SITE_URL=http://localhost:3009 \
#     BACKEND_INTERNAL_URL=http://localhost:8010 bun run dev      # :3009
#
# Credentials come from CONTRACT_USER / CONTRACT_PASSWORD, the same pair
# scripts/snapshot-pull.ts uses. Against the replay any value logs in.
#
# Publishing (--pr): the repo is private, so raw.githubusercontent links do not
# render for reviewers. The shots are pushed to a standalone
# `screenshots/studio` branch — never merged, force-updated each run — and the
# PR comment links them through github.com/<repo>/raw/<branch>/<path>, which is
# session-authenticated and renders inline for anyone who can see the repo.

set -euo pipefail

BASE_URL="${1:-http://localhost:3009}"
[ $# -gt 0 ] && shift

PR_NUMBER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) PR_NUMBER="${2:?--pr needs a PR number}"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

LOGIN_IDENTIFIER="${CONTRACT_USER:-admin}"
LOGIN_PASSWORD="${CONTRACT_PASSWORD:-schwarz123!}"

# Unique session per run: a wedged leftover session would otherwise break every
# subsequent run. Closed again on exit.
SESSION=(--session "studio-shots-$$")
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_ROOT="$REPO_ROOT/screenshots/studio"
SHOT_BRANCH="screenshots/studio"

cd "$REPO_ROOT"

DESKTOP_VIEWPORT=(1680 1000)
MOBILE_VIEWPORT=(390 844)

# Longest a desktop shot may be; taller pages clip at the bottom rather than
# producing an unreadably tall image.
MAX_SHOT_HEIGHT=2400

ab() { agent-browser "${SESSION[@]}" "$@"; }
trap 'ab close >/dev/null 2>&1 || true' EXIT

failures=0

# A screenshot of a broken page still "succeeds", so reject the ways a dev
# server hands back something that looks captured but isn't the page:
#   - a transient 404 while a route recompiles
#   - the runtime/build error overlay, which lives in a shadow root inside
#     <nextjs-portal>. That element is present on every dev page (it also
#     renders the devtools badge), so test its text, not its existence.
#   - our own error boundary (src/app/studio/error.tsx)
page_error() {
  local probe
  probe=$(ab eval "(() => {
    const body = document.body.innerText || '';
    if (body.includes('This page could not be found')) return '404';
    if (body.includes('Something went wrong loading this page')) return 'error-boundary';
    const p = document.querySelector('nextjs-portal');
    const t = p && p.shadowRoot ? p.shadowRoot.textContent || '' : '';
    if (/Runtime Error|Unhandled Runtime Error|Build Error|Failed to compile/.test(t)) return 'error-overlay';
    if (!document.querySelector('h1')) return 'no-content';
    return '';
  })()")
  probe=${probe#\"}
  probe=${probe%\"}
  printf '%s' "$probe"
}

# capture <path> <out.png> <mode>   mode: desktop | mobile
capture() {
  local path="$1" out="$2" mode="$3" attempt err
  mkdir -p "$(dirname "$out")"
  for attempt in 1 2 3; do
    if ab open "$BASE_URL$path" && ab wait --load networkidle; then
      err=$(page_error || true)
      if [ -n "$err" ]; then
        echo "  $err for $path (attempt $attempt), retrying" >&2
      elif capture_shot "$path" "$out" "$mode"; then
        return 0
      fi
    fi
    echo "  retrying $path (attempt $attempt failed)" >&2
    sleep 2
  done
  echo "  giving up on $path" >&2
  failures=$((failures + 1))
  return 1
}

capture_shot() {
  local path="$1" out="$2" mode="$3" h
  if [ "$mode" = mobile ]; then
    # Nothing is position:fixed down the page at phone widths, so Playwright's
    # full-page stitch is correct here.
    ab set viewport "${MOBILE_VIEWPORT[@]}"
    ab wait 250
    ab screenshot --full "$out" || return 1
  else
    # The desktop sidebar is position:fixed, so a --full stitch strands its
    # footer partway down a tall page. Size the viewport to the content instead
    # and take a single-viewport shot. Reset to the baseline height first:
    # scrollHeight never reports below the current viewport, so measuring while
    # the viewport is still tall from the previous page over-reports.
    ab set viewport "${DESKTOP_VIEWPORT[@]}"
    ab wait 200
    h=$(ab eval "Math.ceil(Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))")
    h=${h//[^0-9]/}
    [ -n "$h" ] || return 1
    [ "$h" -gt "$MAX_SHOT_HEIGHT" ] && h=$MAX_SHOT_HEIGHT
    ab set viewport "${DESKTOP_VIEWPORT[0]}" "$h"
    ab wait 250
    ab screenshot "$out" || return 1
  fi
  echo "  captured $path -> ${out#"$REPO_ROOT"/}"
}

# First /studio/runs/<id> href on the current page, or empty. The rows are
# whole-row links (components/table.tsx renders an absolutely positioned <a>).
first_run_href() {
  local href
  href=$(ab eval "(() => {
    const a = document.querySelector('a[href^=\"/studio/runs/\"]');
    return a ? a.getAttribute('href') : '';
  })()")
  href=${href#\"}
  href=${href%\"}
  printf '%s' "$href"
}

# ---------------------------------------------------------------- capture ---

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT/desktop" "$OUT_ROOT/mobile"

ab set viewport "${DESKTOP_VIEWPORT[@]}"
ab open "$BASE_URL/"
ab wait --load networkidle
if ab find first "input[name='identifier']" fill "$LOGIN_IDENTIFIER"; then
  ab find first "input[name='password']" fill "$LOGIN_PASSWORD"
  ab find first "button[type='submit']" click
  ab wait --load networkidle
fi

echo "Runs list:"
capture /studio/runs "$OUT_ROOT/desktop/runs-list.png" desktop || true

# Discover the newest run from the list we are already on.
newest_run=$(first_run_href)

echo "Halted filter:"
capture "/studio/runs?status=halted" "$OUT_ROOT/desktop/runs-halted.png" desktop || true
halted_run=$(first_run_href)

if [ -n "$newest_run" ]; then
  echo "Newest run detail:"
  capture "$newest_run" "$OUT_ROOT/desktop/run-detail.png" desktop || true
else
  echo "  no runs in this workspace — skipping run detail" >&2
fi

if [ -n "$halted_run" ] && [ "$halted_run" != "$newest_run" ]; then
  echo "Halted run detail:"
  capture "$halted_run" "$OUT_ROOT/desktop/run-detail-halted.png" desktop || true
fi

echo "Mobile:"
capture /studio/runs "$OUT_ROOT/mobile/runs-list.png" mobile || true
[ -n "${newest_run:-}" ] && capture "$newest_run" "$OUT_ROOT/mobile/run-detail.png" mobile || true

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures page(s) failed to capture — see the log above." >&2
else
  echo "All pages captured into ${OUT_ROOT#"$REPO_ROOT"/}"
fi

# ---------------------------------------------------------------- publish ---

[ -n "$PR_NUMBER" ] || exit $(( failures > 0 ? 1 : 0 ))

command -v gh >/dev/null || { echo "gh is required to publish" >&2; exit 1; }

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
STAMP=$(date -u +%Y%m%d-%H%M%S)
WORKTREE=$(mktemp -d)
trap 'ab close >/dev/null 2>&1 || true; rm -rf "$WORKTREE"' EXIT

# A standalone branch holding only images, force-updated each run, never merged
# into main — so the screenshots render in the PR without putting binaries in
# the history of the code branches.
git worktree add --detach "$WORKTREE" >/dev/null 2>&1
(
  cd "$WORKTREE"
  git checkout --orphan "$SHOT_BRANCH" >/dev/null 2>&1
  git rm -rq --cached . 2>/dev/null || true
  find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  mkdir -p "$STAMP"
  cp -R "$OUT_ROOT/." "$STAMP/"
  git add "$STAMP"
  git -c user.name="$(git config user.name)" -c user.email="$(git config user.email)" \
      commit -qm "screenshots(studio): $STAMP"
  git push -qf origin "HEAD:$SHOT_BRANCH"
)
git worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true

shot_md() {
  local label="$1" rel="$2"
  [ -f "$OUT_ROOT/$rel" ] || return 0
  printf '### %s\n\n<img src="https://github.com/%s/raw/%s/%s/%s" width="900">\n\n' \
    "$label" "$REPO" "$SHOT_BRANCH" "$STAMP" "$rel"
}

BODY=$(mktemp)
{
  printf '## Studio screenshots\n\n'
  printf '_Captured %s UTC from `%s`. Regenerate with `frontend/scripts/screenshot-studio.sh <base-url> --pr %s`._\n\n' \
    "$(date -u '+%Y-%m-%d %H:%M')" "$BASE_URL" "$PR_NUMBER"
  shot_md 'Runs list' desktop/runs-list.png
  shot_md 'Runs list — halted filter' desktop/runs-halted.png
  shot_md 'Run detail' desktop/run-detail.png
  shot_md 'Run detail — halted run' desktop/run-detail-halted.png
  printf '<details><summary>Mobile</summary>\n\n'
  shot_md 'Runs list (390px)' mobile/runs-list.png
  shot_md 'Run detail (390px)' mobile/run-detail.png
  printf '</details>\n'
} > "$BODY"

gh pr comment "$PR_NUMBER" --body-file "$BODY"
rm -f "$BODY"
echo "Attached screenshots to PR #$PR_NUMBER (branch $SHOT_BRANCH, $STAMP)"

exit $(( failures > 0 ? 1 : 0 ))
