#!/usr/bin/env bash
# ==============================================================================
# Schwarz Research Intelligence - Telemetry & Prometheus Scraper
# Fetches metrics from /api/telemetry/ (JSON Dashboard) and /metrics (Prometheus)
# ==============================================================================

set -eo pipefail

# Configuration (defaults to STACKIT production endpoint; override via env vars)
HOST="${HOST:-https://sri-prod.apps.01.cf.eu01.onstackit.cloud}"
USER_NAME="${USER_NAME:-admin}"
USER_PASSWORD="${USER_PASSWORD:-schwarz123!}"
API_KEY="${API_KEY:-admin_mcp_key:schwarz123!}"

echo "======================================================================"
echo "1. Authenticating and fetching JWT token from $HOST/api/auth/login/..."
echo "======================================================================"

LOGIN_RESP=$(curl -s -X POST "$HOST/api/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"username_or_email\":\"$USER_NAME\",\"password\":\"$USER_PASSWORD\"}")

ACCESS_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys, json; print(json.loads(sys.stdin.read()).get('access', ''))")

if [ -z "$ACCESS_TOKEN" ]; then
    echo "Authentication failed:"
    echo "$LOGIN_RESP"
    exit 1
fi
echo "Authenticated successfully. Acquired JWT Bearer token."

echo ""
echo "======================================================================"
echo "2. Telemetry JSON Dashboard from $HOST/api/telemetry/"
echo "======================================================================"

TELEMETRY_JSON=$(curl -s -X GET "$HOST/api/telemetry/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

export TELEMETRY_JSON
python3 - <<'EOF'
import os
import json
import sys

raw = os.environ.get('TELEMETRY_JSON', '{}')
try:
    data = json.loads(raw)
    funnel = data.get('funnel', {})
    rates = funnel.get('conversion_rates', {})
    status_map = funnel.get('status_breakdown', {})
    econ = data.get('economics', {})
    tokens = econ.get('tokens', {})
    cache = data.get('cache_efficiency', {})
    fleet = data.get('fleet_health', {})
    comp = data.get('latencies', {}).get('components', {})

    print("SLR PIPELINE FUNNEL & CONVERSION:")
    print(f"  • Total papers ingested  : {funnel.get('total_papers', 0)}")
    print(f"  • Accepted technologies  : {status_map.get('accepted', 0)}")
    print(f"  • Abstract Pass Rate     : {rates.get('abstract_pass_pct', 0.0)}%")
    print(f"  • Full-Text Pass Rate    : {rates.get('full_text_pass_pct', 0.0)}%")
    print(f"  • End-to-End Yield       : {rates.get('end_to_end_yield_pct', 0.0)}% (papers reaching final report)")
    print(f"  • Status Breakdown       : {status_map}")

    print("\nLLM COSTS & TOKEN CONSUMPTION:")
    print(f"  • Total platform cost    : ${econ.get('total_platform_usd', 0.0):.4f} USD")
    print(f"    ├── Pipeline (SLR)     : ${econ.get('pipeline_usd', 0.0):.4f} USD")
    print(f"    └── Chat (Ask Paper)   : ${econ.get('chat_usd', 0.0):.4f} USD")
    print(f"  • Total tokens consumed  : {tokens.get('tokens_consumed_total', 0):,} tokens")
    print(f"  • Avg cost / accepted paper: ${econ.get('per_paper_metrics', {}).get('cost_per_accepted_paper_avg_usd', 0.0):.4f} USD")
    print(f"  • Avg cost / SLR run       : ${econ.get('per_run_metrics', {}).get('cost_per_run_avg_usd', 0.0):.4f} USD")

    print("\nDOCUMENT REGISTRY CACHE SAVINGS:")
    print(f"  • Cached unique PDFs     : {cache.get('cached_documents_count', 0)}")
    print(f"  • Cache hits (re-use)    : {cache.get('cache_hits_total', 0)}")
    print(f"  • Bandwidth saved        : {cache.get('bandwidth_saved_mb', 0.0)} MB")

    print("\nCOMPONENT EXECUTION LATENCY (Avg / P95 / Max):")
    for k, v in comp.items():
        print(f"  • {k.ljust(24)}: Avg: {v.get('avg_seconds', 0.0)}s | P95: {v.get('p95_seconds', 0.0)}s | Max: {v.get('max_seconds', 0.0)}s (Runs: {v.get('count', 0)})")

    print("\nFLEET HEALTH & SYSTEM STATE:")
    print(f"  • Active workspaces      : {fleet.get('active_workspaces', 0)}")
    print(f"  • Parameter extractions  : {fleet.get('extractions_total', 0)} ({fleet.get('extractions_validated', 0)} validated HITL)")
    print(f"  • Chat sessions / msgs   : {fleet.get('chat_sessions_total', 0)} / {fleet.get('chat_messages_total', 0)}")
except Exception as e:
    print(f"Parsing error: {e}\nRaw output:", raw[:500])
EOF

echo ""
echo "======================================================================"
echo "3. Prometheus Metrics from $HOST/metrics"
echo "======================================================================"

PROMETHEUS_OUTPUT=$(curl -s -X GET "$HOST/metrics" \
  -H "X-API-Key: $API_KEY" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "$PROMETHEUS_OUTPUT" | grep -E '^(sri_papers_total|sri_llm_cost|sri_pipeline_conversion|sri_document_registry|sri_workspaces|sri_agent_processes)' | head -n 25

echo ""
echo "Done."
