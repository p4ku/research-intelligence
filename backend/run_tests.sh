#!/usr/bin/env bash
# ==============================================================================
# Schwarz Research Intelligence - Fast Parallel Backend Test Runner with Coverage
# Executes complete test suite using in-memory SQLite, auto-parallelization,
# and generates real-time code coverage metrics upon test completion.
# ==============================================================================

set -e

# Resolve directory paths (supports running from repo root or backend directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${SCRIPT_DIR}"

# 1. Detect Python interpreter (.venv at root, venv in backend, or system python)
if [ -f "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
elif [ -f "${SCRIPT_DIR}/venv/bin/python" ]; then
    PYTHON_BIN="${SCRIPT_DIR}/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "❌ Error: Python interpreter not found."
    exit 1
fi

# 2. Detect Coverage binary
if [ -f "${PROJECT_ROOT}/.venv/bin/coverage" ]; then
    COVERAGE_BIN="${PROJECT_ROOT}/.venv/bin/coverage"
elif [ -f "${SCRIPT_DIR}/venv/bin/coverage" ]; then
    COVERAGE_BIN="${SCRIPT_DIR}/venv/bin/coverage"
elif command -v coverage >/dev/null 2>&1; then
    COVERAGE_BIN="coverage"
else
    COVERAGE_BIN=""
fi

echo "============================================="
echo "🧪 Running SRI Backend Test Suite in Parallel..."
echo "📍 Python interpreter : ${PYTHON_BIN}"
echo "============================================="

if [ -n "$COVERAGE_BIN" ]; then
    echo "📊 Coverage tracking enabled ($COVERAGE_BIN)"
    "$COVERAGE_BIN" erase
    
    if [ $# -gt 0 ]; then
        "$COVERAGE_BIN" run manage.py test "$@"
    else
        "$COVERAGE_BIN" run manage.py test --parallel auto research_intelligence.tests mcp_server chat
    fi
    
    echo ""
    echo "================================================================================"
    echo "📊 Code Coverage Summary (Application Logic):"
    echo "================================================================================"
    "$COVERAGE_BIN" combine --quiet 2>/dev/null || true
    "$COVERAGE_BIN" report
else
    if [ $# -gt 0 ]; then
        exec "$PYTHON_BIN" manage.py test "$@"
    else
        exec "$PYTHON_BIN" manage.py test --parallel auto research_intelligence.tests mcp_server chat
    fi
fi
