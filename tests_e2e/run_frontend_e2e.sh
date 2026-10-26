#!/usr/bin/env bash
# ==============================================================================
# 🚀 Schwarz Research Intelligence - Next.js Frontend E2E Test Runner (TypeScript / Playwright)
# ==============================================================================
# Usage:
#   ./tests_e2e/run_frontend_e2e.sh                     # Runs all TS specs on Local dev (Default, http://localhost:3000)
#   ./tests_e2e/run_frontend_e2e.sh staging             # Runs on Staging
#   ./tests_e2e/run_frontend_e2e.sh prod                # Runs on Prod
#   ./tests_e2e/run_frontend_e2e.sh --ui                # Opens Playwright Interactive UI Mode
#   ./tests_e2e/run_frontend_e2e.sh --headed            # Opens visible Chrome browser
#   ./tests_e2e/run_frontend_e2e.sh settings            # Runs specs/settings.spec.ts
#   ./tests_e2e/run_frontend_e2e.sh auth                # Runs specs/auth.spec.ts
#   ./tests_e2e/run_frontend_e2e.sh --report            # Opens HTML test execution report
# ==============================================================================

set -e

# Resolve project root and tests_e2e directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TESTS_DIR="${PROJECT_ROOT}/tests_e2e"

cd "${TESTS_DIR}"

# 1. Ensure node_modules are installed
if [ ! -d "${TESTS_DIR}/node_modules" ]; then
    echo "📦 Node modules missing in tests_e2e. Installing dependencies with npm..."
    npm install
fi

# 2. Parse target environment and arguments
TARGET="local"
TARGET_SET=false
SPEC_FILTER=""
EXTRA_ARGS=()
UI_MODE=false
SHOW_REPORT=false

for arg in "$@"; do
    arg_lower=$(echo "$arg" | tr '[:upper:]' '[:lower:]')
    case "${arg_lower}" in
        prod|production)
            TARGET="prod"
            TARGET_SET=true
            ;;
        staging|stage)
            TARGET="staging"
            TARGET_SET=true
            ;;
        local|localhost|dev)
            TARGET="local"
            TARGET_SET=true
            ;;
        annotate|annotate.soinventive.co.uk|slr.soinventive.co.uk|http://*|https://*|*.*|*:*)
            TARGET="$arg"
            TARGET_SET=true
            ;;
        slr)
            if [ "$TARGET_SET" = true ]; then
                SPEC_FILTER="specs/10_slr_review_gates.journey.spec.ts"
            else
                TARGET="slr"
                TARGET_SET=true
            fi
            ;;
        --ui)
            UI_MODE=true
            EXTRA_ARGS+=("--ui")
            ;;
        --report|report)
            SHOW_REPORT=true
            ;;
        --headed)
            EXTRA_ARGS+=("--headed")
            ;;
        --debug)
            EXTRA_ARGS+=("--debug")
            ;;
        slr_console|console|slr_stage_2|specs/11*|11)
            SPEC_FILTER="specs/11_slr_console_prisma_rob.journey.spec.ts"
            ;;
        slr_gates|slr_audit|slr_review|audit|audit_queue|specs/10*|10|--scenario=slr*)
            SPEC_FILTER="specs/10_slr_review_gates.journey.spec.ts"
            ;;
        settings|--scenario=settings|specs/settings.spec.ts)
            SPEC_FILTER="specs/settings.spec.ts"
            ;;
        auth|--scenario=auth|specs/auth.spec.ts)
            SPEC_FILTER="specs/auth.spec.ts"
            ;;
        navigation|--scenario=navigation|specs/navigation.spec.ts)
            SPEC_FILTER="specs/navigation.spec.ts"
            ;;
        workspace|--scenario=workspace|specs/workspace.spec.ts)
            SPEC_FILTER="specs/workspace.spec.ts"
            ;;
        papers|--scenario=papers|specs/papers.spec.ts)
            SPEC_FILTER="specs/papers.spec.ts"
            ;;
        i18n|--scenario=i18n|specs/i18n.spec.ts)
            SPEC_FILTER="specs/i18n.spec.ts"
            ;;
        ask|--scenario=ask|specs/ask.spec.ts)
            SPEC_FILTER="specs/ask.spec.ts"
            ;;
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

if [ "$SHOW_REPORT" = true ]; then
    echo "📊 Opening Playwright HTML report..."
    exec npx playwright show-report
fi

TARGET_UPPER=$(echo "$TARGET" | tr '[:lower:]' '[:upper:]')

echo "=================================================================="
echo "🧪 Running Schwarz Research Intelligence Frontend E2E (TypeScript)..."
echo "📍 Target Environment : ${TARGET_UPPER}"
echo "📍 Test Directory      : ${TESTS_DIR}"
if [ -n "${SPEC_FILTER}" ]; then
    echo "📍 Selected Spec       : ${SPEC_FILTER}"
fi
echo "=================================================================="

export E2E_TARGET_ENV="${TARGET}"

if [ -n "${SPEC_FILTER}" ]; then
    exec npx playwright test "${SPEC_FILTER}" "${EXTRA_ARGS[@]}"
else
    exec npx playwright test "${EXTRA_ARGS[@]}"
fi

