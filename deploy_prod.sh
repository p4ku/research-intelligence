#!/usr/bin/env bash
# ==============================================================================
# Production Deployment & Restart Script for SRI / SLR (Docker Swarm Mode)
# Builds container images, exports .env, updates Swarm stack and rolls services.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-prod.yml}"
STACK_NAME="${1:-${STACK_NAME:-sri-prod}}"

echo "======================================================================"
echo "🚀 Deploying SLR Platform to Docker Swarm: ${STACK_NAME}"
echo "📁 Compose file : ${COMPOSE_FILE}"
echo "======================================================================"

# 0. Load environment variables from .env if present (CRITICAL for docker stack deploy)
# Note: Variables already exported in the parent script take precedence!
if [ -f .env ]; then
  echo "📋 Loading default environment variables from .env (preserving parent exports)..."
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      \#*|"") continue ;;
    esac
    var_name="${line%%=*}"
    var_name="$(echo "$var_name" | xargs)"
    if [ -n "$var_name" ] && [ -z "${!var_name+x}" ]; then
      eval "export $line" 2>/dev/null || true
    fi
  done < .env
else
  echo "ℹ️ No local .env file found; using active shell environment variables."
fi

# Ensure Swarm mode is active
if ! docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -qi "active"; then
  echo "⚠️ Docker Swarm is not active on this host. Initializing single-node Swarm..."
  docker swarm init || true
fi

# 1. Build container images (reads build args and local Dockerfiles)
echo -e "\n📦 [1/3] Building container images with ${COMPOSE_FILE}..."
docker compose -f "${COMPOSE_FILE}" build

# 2. Deploy / update stack definition in Docker Swarm
echo -e "\n🚀 [2/3] Deploying / Updating Docker Swarm stack '${STACK_NAME}'..."
docker stack deploy -c "${COMPOSE_FILE}" "${STACK_NAME}"

# 3. Force-rolling restart of services to pick up newly built images
echo -e "\n🔄 [3/3] Forcing zero-downtime service rolling restart..."
SERVICES=("api" "mcp" "worker" "beat" "frontend")
for svc in "${SERVICES[@]}"; do
  SERVICE_NAME="${STACK_NAME}_${svc}"
  if docker service inspect "${SERVICE_NAME}" >/dev/null 2>&1; then
    echo "  -> Updating service: ${SERVICE_NAME}..."
    docker service update --force "${SERVICE_NAME}" >/dev/null
  else
    echo "  -> Service ${SERVICE_NAME} not yet running; will be started by Swarm."
  fi
done

echo -e "\n📊 Current Stack Status:"
docker stack services "${STACK_NAME}"

echo -e "\n✅ All ${STACK_NAME} services were successfully deployed and restarted!"
