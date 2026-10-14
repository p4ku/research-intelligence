#!/usr/bin/env bash
# ==============================================================================
# Set STACKIT Cloud Foundry Environment Variables & Secrets
# Configures backend and frontend environment variables across all 5 SRI apps.
# ==============================================================================

set -euo pipefail

# 1. Observability (Sentry DSN)
export SENTRY_DSN="${SENTRY_DSN:-https://155678a8610461ae7c7eecdfdd0583a4@o4511999152291840.ingest.de.sentry.io/4511999157010512}"

# 2. Database (STACKIT PostgreSQL Flex)
DB_HOST="${DB_HOST:-postgres.internal.stackit}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-research_intelligence}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_SSLMODE="${DB_SSLMODE:-require}"

# 3. Redis Broker & Cache (STACKIT Redis)
REDIS_URL="${REDIS_URL:-}"

# 4. Object Storage (STACKIT S3-compatible Object Storage)
STORAGE_BACKEND="${STORAGE_BACKEND:-s3}"
AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-}"
AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-}"
AWS_STORAGE_BUCKET_NAME="${AWS_STORAGE_BUCKET_NAME:-schwarz-research-intelligence}"
AWS_S3_ENDPOINT_URL="${AWS_S3_ENDPOINT_URL:-https://object.storage.eu01.onstackit.cloud}"
AWS_S3_REGION_NAME="${AWS_S3_REGION_NAME:-eu01}"

# 5. Application & AI Keys
SECRET_KEY="${SECRET_KEY:-}"
GEMINI_API_KEY="${GEMINI_API_KEY:-}"

# 6. Endpoints
BACKEND_INTERNAL_URL="${BACKEND_INTERNAL_URL:-https://sri-prod.apps.01.cf.eu01.onstackit.cloud}"
SITE_URL="${SITE_URL:-https://sri-prod.apps.01.cf.eu01.onstackit.cloud}"

echo "Configuring Backend Applications (sri-api, sri-worker, sri-beat, sri-mcp)..."
for APP in sri-api sri-worker sri-beat sri-mcp; do
  echo "Setting environment for $APP..."
  cf set-env "$APP" DB_HOST "$DB_HOST"
  cf set-env "$APP" DB_PORT "$DB_PORT"
  cf set-env "$APP" DB_NAME "$DB_NAME"
  cf set-env "$APP" DB_USER "$DB_USER"
  [ -n "$DB_PASSWORD" ] && cf set-env "$APP" DB_PASSWORD "$DB_PASSWORD"
  cf set-env "$APP" DB_SSLMODE "$DB_SSLMODE"

  [ -n "$REDIS_URL" ] && cf set-env "$APP" REDIS_URL "$REDIS_URL"

  cf set-env "$APP" STORAGE_BACKEND "$STORAGE_BACKEND"
  [ -n "$AWS_ACCESS_KEY_ID" ] && cf set-env "$APP" AWS_ACCESS_KEY_ID "$AWS_ACCESS_KEY_ID"
  [ -n "$AWS_SECRET_ACCESS_KEY" ] && cf set-env "$APP" AWS_SECRET_ACCESS_KEY "$AWS_SECRET_ACCESS_KEY"
  cf set-env "$APP" AWS_STORAGE_BUCKET_NAME "$AWS_STORAGE_BUCKET_NAME"
  cf set-env "$APP" AWS_S3_ENDPOINT_URL "$AWS_S3_ENDPOINT_URL"
  cf set-env "$APP" AWS_S3_REGION_NAME "$AWS_S3_REGION_NAME"

  cf set-env "$APP" SENTRY_DSN "$SENTRY_DSN"

  [ -n "$SECRET_KEY" ] && cf set-env "$APP" SECRET_KEY "$SECRET_KEY"
  [ -n "$GEMINI_API_KEY" ] && cf set-env "$APP" GEMINI_API_KEY "$GEMINI_API_KEY"
done

echo "Configuring Frontend Application (sri-frontend)..."
cf set-env sri-frontend NODE_ENV production
cf set-env sri-frontend NEXT_PUBLIC_API_URL "${BACKEND_INTERNAL_URL}/api/v1"
cf set-env sri-frontend NEXT_PUBLIC_MCP_URL "${BACKEND_INTERNAL_URL}/sse"
cf set-env sri-frontend BACKEND_INTERNAL_URL "$BACKEND_INTERNAL_URL"
cf set-env sri-frontend SITE_URL "$SITE_URL"

echo "Environment configuration complete. Restarting applications..."
cf restart sri-api
cf restart sri-mcp
cf restart sri-worker
cf restart sri-beat
cf restart sri-frontend

echo "All applications updated and restarted."
