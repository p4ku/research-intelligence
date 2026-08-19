#!/usr/bin/env bash
# ==============================================================================
# Schwarz Research Intelligence - Fast Parallel Test Runner
# Executes complete test suite using in-memory SQLite and auto-parallelization.
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

echo "🧪 Running Schwarz Research Intelligence Test Suite in Parallel..."
echo "📍 Python interpreter: $PYTHON_BIN"

# If arguments are passed, pass them directly (e.g. ./run_tests.sh research_intelligence.tests.test_mcp_server)
# Otherwise, default to full test suite with --parallel auto
if [ $# -gt 0 ]; then
    exec "$PYTHON_BIN" backend/manage.py test "$@"
else
    exec "$PYTHON_BIN" backend/manage.py test --parallel auto research_intelligence.tests
fi
