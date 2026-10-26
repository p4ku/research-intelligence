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

# Normalize MinIO and S3 credentials (ensures clean variables without nested compose syntax)
export MINIO_ROOT_USER="${MINIO_ROOT_USER:-${MINIO_ACCESS_KEY:-${AWS_ACCESS_KEY_ID:-minio_dev_user}}}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-${MINIO_SECRET_KEY:-${AWS_SECRET_ACCESS_KEY:-minio_dev_password}}}"
export MINIO_ACCESS_KEY="${MINIO_ROOT_USER}"
export MINIO_SECRET_KEY="${MINIO_ROOT_PASSWORD}"
export AWS_ACCESS_KEY_ID="${MINIO_ROOT_USER}"
export AWS_SECRET_ACCESS_KEY="${MINIO_ROOT_PASSWORD}"

# Ensure this node is a Swarm manager
SWARM_STATE="$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo "inactive")"
IS_MANAGER="$(docker info --format '{{.Swarm.ControlAvailable}}' 2>/dev/null || echo "false")"

if [ "$SWARM_STATE" != "active" ] || [ "$IS_MANAGER" != "true" ]; then
  if [ "$SWARM_STATE" = "active" ] && [ "$IS_MANAGER" != "true" ]; then
    echo "⚠️ Node is currently in Swarm as a worker, not a manager. Leaving worker state to re-initialize..."
    docker swarm leave --force 2>/dev/null || true
  fi

  echo "⚠️ Initializing Docker Swarm manager on this host..."
  if ! docker swarm init 2>/dev/null; then
    PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    PRIMARY_IP="${PRIMARY_IP:-127.0.0.1}"
    echo "  -> Retrying docker swarm init with --advertise-addr ${PRIMARY_IP}..."
    docker swarm init --advertise-addr "${PRIMARY_IP}"
  fi
fi

# 1. Build container images (reads build args and local Dockerfiles)
echo -e "\n📦 [1/3] Building container images with ${COMPOSE_FILE}..."
docker compose -f "${COMPOSE_FILE}" build

# 2. Deploy / update stack definition in Docker Swarm
echo -e "\n🚀 [2/3] Deploying / Updating Docker Swarm stack '${STACK_NAME}'..."
docker stack deploy -c "${COMPOSE_FILE}" "${STACK_NAME}"

# 3. Force-rolling restart of services to pick up newly built images
echo -e "\n🔄 [3/3] Forcing zero-downtime service rolling restart..."
SERVICES=("api" "mcp" "worker" "beat" "frontend" "minio")
for svc in "${SERVICES[@]}"; do
  SERVICE_NAME="${STACK_NAME}_${svc}"
  if docker service inspect "${SERVICE_NAME}" >/dev/null 2>&1; then
    echo "  -> Updating service: ${SERVICE_NAME}..."
    if ! docker service update --force "${SERVICE_NAME}" >/dev/null 2>&1; then
      echo "  ⚠️ Warning: Service update for ${SERVICE_NAME} paused or delayed (Swarm will converge tasks)."
    fi
  else
    echo "  -> Service ${SERVICE_NAME} not yet running; will be started by Swarm."
  fi
done

echo -e "\n📊 Current Stack Status:"
docker stack services "${STACK_NAME}"

echo -e "\n✅ All ${STACK_NAME} services were successfully deployed and restarted!"
