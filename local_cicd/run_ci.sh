#!/usr/bin/env bash
# ==============================================================================
# Local Continuous Integration (CI) Pipeline
# Executes syntax validation, Django system check, and the full parallel test suite.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 1. Load local environment configuration
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "📋 Loading local environment from $SCRIPT_DIR/.env..."
    # shellcheck disable=SC1091
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

cd "$ROOT_DIR"

# 2. Colors for terminal output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cleanup_ci() {
    echo -e "\n${BLUE}🧹 Cleaning up temporary CI/test artifacts...${NC}"
    rm -rf "$ROOT_DIR/.coverage" "$ROOT_DIR"/.coverage.* "$ROOT_DIR/htmlcov" "$ROOT_DIR/prototype/tmp" 2>/dev/null || true
    echo -e "${GREEN}✨ CI Cleanup completed.${NC}"
}
trap cleanup_ci EXIT

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}🚀 STARTING LOCAL CI PIPELINE${NC}"
echo -e "${BLUE}======================================================================${NC}"

# 3. Detect Python interpreter
if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo -e "${RED}❌ Error: Python interpreter not found in .venv or system PATH.${NC}"
    exit 1
fi

echo -e "📍 Python binary: ${GREEN}$PYTHON_BIN${NC}"

# 4. Django System Checks & Migrations Check
echo -e "\n${BLUE}[1/3] Running Django System & Configuration Integrity Checks...${NC}"
"$PYTHON_BIN" backend/manage.py check
echo -e "${GREEN}✅ Django system check passed with 0 issues.${NC}"

# 5. Execute Full Parallel Test Suite (Django & FastMCP)
echo -e "\n${BLUE}[2/3] Running Full Parallel Test Suite (Zero-token in-memory SQLite)...${NC}"
"$ROOT_DIR/backend/run_tests.sh"
echo -e "${GREEN}✅ Full test suite passed successfully!${NC}"

# 6. Execute FastMCP Server Tests
echo -e "\n${BLUE}[3/3] Running FastMCP Protocol Test Suite...${NC}"
"$ROOT_DIR/backend/run_tests.sh" mcp_server
echo -e "${GREEN}✅ FastMCP test suite passed successfully!${NC}"

echo -e "\n${GREEN}======================================================================${NC}"
echo -e "${GREEN}🎉 LOCAL CI PIPELINE COMPLETED SUCCESSFULLY!${NC}"
echo -e "${GREEN}======================================================================${NC}"
