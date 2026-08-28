#!/usr/bin/env bash
# ==============================================================================
# Schwarz Research Intelligence - Fast Parallel Test Runner with Dynamic Coverage
# Executes complete test suite using in-memory SQLite, auto-parallelization,
# and generates real-time code coverage metrics upon test completion.
# ==============================================================================

set -e

# Resolve project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Detect Python interpreter (.venv or system python)
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "❌ Error: Python interpreter not found."
    exit 1
fi

# Detect Coverage binary
if [ -f ".venv/bin/coverage" ]; then
    COVERAGE_BIN=".venv/bin/coverage"
elif command -v coverage >/dev/null 2>&1; then
    COVERAGE_BIN="coverage"
else
    COVERAGE_BIN=""
fi

echo "🧪 Running Schwarz Research Intelligence Test Suite in Parallel..."
echo "📍 Python interpreter: $PYTHON_BIN"

if [ -n "$COVERAGE_BIN" ]; then
    echo "📊 Coverage tracking enabled ($COVERAGE_BIN)"
    "$COVERAGE_BIN" erase
    
    if [ $# -gt 0 ]; then
        "$COVERAGE_BIN" run backend/manage.py test "$@"
    else
        "$COVERAGE_BIN" run backend/manage.py test --parallel auto research_intelligence.tests mcp_server chat
    fi
    
    echo ""
    echo "================================================================================"
    echo "📊 Code Coverage Summary (Application Logic):"
    echo "================================================================================"
    "$COVERAGE_BIN" combine --quiet 2>/dev/null || true
    "$COVERAGE_BIN" report
else
    if [ $# -gt 0 ]; then
        exec "$PYTHON_BIN" backend/manage.py test "$@"
    else
        exec "$PYTHON_BIN" backend/manage.py test --parallel auto research_intelligence.tests mcp_server chat
    fi
fi
