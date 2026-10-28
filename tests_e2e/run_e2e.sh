#!/usr/bin/env bash
# ==============================================================================
# 🚀 Research Intelligence - Live E2E Pipeline Simulator & Test Runner
# ==============================================================================
# Usage:
#   ./tests_e2e/run_e2e.sh                    # Runs against Production (Default LLM: google)
#   ./tests_e2e/run_e2e.sh staging            # Runs against Staging
#   ./tests_e2e/run_e2e.sh annotate slr_gates # Runs SLR Gates against annotate.soinventive.co.uk
#   ./tests_e2e/run_e2e.sh annotate slr_gates --openrouter # Runs SLR Gates with OpenRouter
#   ./tests_e2e/run_e2e.sh local              # Runs against Local development server
#   ./tests_e2e/run_e2e.sh comments           # Runs Paper Comments & Collaboration API E2E
#   ./tests_e2e/run_e2e.sh local comments     # Runs Comments API E2E on Local dev server
#   ./tests_e2e/run_e2e.sh --cleanup-after    # Runs on Prod and deletes workspace at end
#   ./tests_e2e/run_e2e.sh prod --limit=20    # Custom paper limit
# ==============================================================================

set -e

# Resolve project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Activate virtualenv if present
if [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
    source "${PROJECT_ROOT}/.venv/bin/activate"
elif [ -f "${PROJECT_ROOT}/venv/bin/activate" ]; then
    source "${PROJECT_ROOT}/venv/bin/activate"
fi

PYTHON_EXEC="python3"
if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PYTHON_EXEC="${PROJECT_ROOT}/.venv/bin/python"
fi

# Detect first argument target shortcut (prod, staging, local)
TARGET="prod"
EXTRA_ARGS=()
TARGET_SET=false
LLM_PROVIDER="${E2E_LLM_PROVIDER:-google}"
LLM_MODEL="${E2E_LLM_MODEL:-google/gemini-3.8-flash}"

for arg in "$@"; do
    arg_lower=$(echo "$arg" | tr '[:upper:]' '[:lower:]')
    case "${arg_lower}" in
        prod|production)
            TARGET="prod"
            TARGET_SET=true
            ;;
        staging|stage|dev)
            TARGET="staging"
            TARGET_SET=true
            ;;
        local|localhost)
            TARGET="local"
            TARGET_SET=true
            ;;
        --openrouter|--opentouter|openrouter|opentouter|--open-router)
            LLM_PROVIDER="openrouter"
            ;;
        --google|--google-ai|google)
            LLM_PROVIDER="google"
            ;;
        --llm-provider=*)
            LLM_PROVIDER="${arg#*=}"
            ;;
        --llm-model=*)
            LLM_MODEL="${arg#*=}"
            ;;
        annotate|annotate.soinventive.co.uk|slr.soinventive.co.uk|http://*|https://*|*.*|*:*)
            TARGET="$arg"
            TARGET_SET=true
            ;;
        slr)
            if [ "$TARGET_SET" = true ]; then
                EXTRA_ARGS+=("--scenario=slr_gates")
            else
                TARGET="slr"
                TARGET_SET=true
            fi
            ;;
        slr_gates|slr_audit|slr_review|slr-gates|slr-audit|slr-review)
            EXTRA_ARGS+=("--scenario=slr_gates")
            ;;
        all)
            EXTRA_ARGS+=("--scenario=all")
            ;;
        comments|comment|collaboration|messages)
            EXTRA_ARGS+=("--scenario=comments")
            ;;
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

TARGET_UPPER=$(echo "$TARGET" | tr '[:lower:]' '[:upper:]')
LLM_PROVIDER_UPPER=$(echo "$LLM_PROVIDER" | tr '[:lower:]' '[:upper:]')

echo "=================================================================="
echo "🧪 Running Research Intelligence Live E2E Pipeline..."
echo "📍 Target Environment : ${TARGET_UPPER}"
echo "📍 LLM Provider        : ${LLM_PROVIDER_UPPER} ($LLM_PROVIDER)"
echo "📍 LLM Model           : ${LLM_MODEL}"
echo "📍 Python Interpreter : ${PYTHON_EXEC}"
echo "=================================================================="

export E2E_TARGET_ENV="${TARGET}"
export E2E_LLM_PROVIDER="${LLM_PROVIDER}"
export E2E_LLM_MODEL="${LLM_MODEL}"

exec "${PYTHON_EXEC}" -m tests_e2e.run_e2e --target="${TARGET}" --llm-provider="${LLM_PROVIDER}" --llm-model="${LLM_MODEL}" "${EXTRA_ARGS[@]}"
