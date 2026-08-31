#!/usr/bin/env bash
# Convenience wrapper redirecting to backend test runner
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/backend/run_tests.sh" "$@"
