#!/usr/bin/env bash
# ==============================================================================
# 🚀 Schwarz Research Intelligence - Next.js Frontend E2E Test Runner
# ==============================================================================
# Usage:
#   ./tests_e2e/run_frontend_e2e.sh                    # Runs on Prod (Default)
#   ./tests_e2e/run_frontend_e2e.sh staging            # Runs on Staging
#   ./tests_e2e/run_frontend_e2e.sh local              # Runs on Local dev
#   ./tests_e2e/run_frontend_e2e.sh --scenario=settings# Runs specific scenario
#   ./tests_e2e/run_frontend_e2e.sh --headed           # Opens visible browser
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

for arg in "$@"; do
    arg_lower=$(echo "$arg" | tr '[:upper:]' '[:lower:]')
    case "${arg_lower}" in
        prod|production)
            TARGET="prod"
            ;;
        staging|stage|dev)
            TARGET="staging"
            ;;
        local|localhost)
            TARGET="local"
            ;;
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

TARGET_UPPER=$(echo "$TARGET" | tr '[:lower:]' '[:upper:]')

echo "=================================================================="
echo "🧪 Running Schwarz Research Intelligence Frontend E2E Test Suite..."
echo "📍 Target Environment : ${TARGET_UPPER}"
echo "📍 Python Interpreter : ${PYTHON_EXEC}"
echo "=================================================================="

exec "${PYTHON_EXEC}" -m tests_e2e.run_frontend_e2e --target="${TARGET}" "${EXTRA_ARGS[@]}"
