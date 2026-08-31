#!/usr/bin/env bash
# ==============================================================================
# State-of-the-Art Local Continuous Deployment (CD) Pipeline
# Builds multi-arch container images (linux/amd64), tags, pushes to STACKIT Harbor,
# and executes Cloud Foundry rolling deployments with post-deploy health verification.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CD_START_TIME=$(date +%s)

# 1. Load local environment configuration
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "📋 Loading local environment from $SCRIPT_DIR/.env..."
    # shellcheck disable=SC1091
    set -a
    _SAVED_DEPLOY_TARGET="$DEPLOY_TARGET"
    _SAVED_SKIP_TESTS="$SKIP_TESTS"
    _SAVED_SKIP_IMAGE_BUILD="$SKIP_IMAGE_BUILD"
    source "$SCRIPT_DIR/.env"
    [ -n "$_SAVED_DEPLOY_TARGET" ] && DEPLOY_TARGET="$_SAVED_DEPLOY_TARGET"
    [ -n "$_SAVED_SKIP_TESTS" ] && SKIP_TESTS="$_SAVED_SKIP_TESTS"
    [ -n "$_SAVED_SKIP_IMAGE_BUILD" ] && SKIP_IMAGE_BUILD="$_SAVED_SKIP_IMAGE_BUILD"
    set +a
else
    echo "⚠️ Warning: $SCRIPT_DIR/.env not found. Please create one based on .env.example."
fi

cd "$ROOT_DIR"

# Colors for terminal output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Automated cleanup on exit (normal, error, or interrupted)
cleanup_cd() {
    echo -e "\n${BLUE}🧹 Cleaning up deployment artifacts & sensitive variables...${NC}"
    # If Docker images were built locally, remove local tagged images to free disk space
    if [ "$SKIP_IMAGE_BUILD" != "true" ] && [ "$DEPLOY_TARGET" != "dry-run" ] && command -v docker >/dev/null 2>&1; then
        echo -e "🗑️ Removing local Docker build images ($BACKEND_IMAGE, $FRONTEND_IMAGE)..."
        docker rmi "$BACKEND_IMAGE" "$FRONTEND_IMAGE" 2>/dev/null || true
        docker image prune -f 2>/dev/null || true
    fi
    # Clean temporary coverage and test dirs
    rm -rf "$ROOT_DIR/.coverage" "$ROOT_DIR"/.coverage.* "$ROOT_DIR/prototype/tmp" 2>/dev/null || true
    # Unset sensitive variables from current subshell environment
    unset REGISTRY_PASSWORD CF_DOCKER_PASSWORD CF_PASSWORD
    ELAPSED=$(( $(date +%s) - CD_START_TIME ))
    echo -e "${GREEN}✨ CD Pipeline finished in ${ELAPSED}s.${NC}"
}
trap cleanup_cd EXIT

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BOLD}${BLUE}🚀 SCHWARZ RESEARCH INTELLIGENCE — LOCAL CD PIPELINE${NC}"
echo -e "${BLUE}======================================================================${NC}"

# Target Defaults & Configuration
DEPLOY_TARGET="${DEPLOY_TARGET:-cf}"
CF_API_URL="${CF_API_URL:-https://api.system.01.cf.eu01.stackit.cloud}"
CF_ORG="${CF_ORG:-organization-sri-production}"
CF_SPACE="${CF_SPACE:-sri-prod}"
REGISTRY_HOST="${REGISTRY_HOST:-registry.onstackit.cloud}"
BACKEND_IMAGE="${BACKEND_IMAGE:-registry.onstackit.cloud/sri-production/sri-backend:latest}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-registry.onstackit.cloud/sri-production/sri-frontend:latest}"
CF_MANIFEST="${CF_MANIFEST:-manifest.yml}"
CF_VARS_FILE="${CF_VARS_FILE:-vars.yml}"
TARGET_PLATFORM="${TARGET_PLATFORM:-linux/amd64}"
GIT_COMMIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'local')"

echo -e "🎯 Deployment Target : ${CYAN}$DEPLOY_TARGET${NC}"
echo -e "🌐 Cloud Foundry      : ${CYAN}$CF_ORG / $CF_SPACE${NC} (${CYAN}$CF_API_URL${NC})"
echo -e "📦 Container Images   : ${CYAN}$BACKEND_IMAGE${NC}"
echo -e "                      : ${CYAN}$FRONTEND_IMAGE${NC}"
echo -e "💻 Target Platform   : ${CYAN}$TARGET_PLATFORM${NC} (Cross-compiled for STACKIT Linux x86)"
echo -e "🔖 Git Commit SHA     : ${CYAN}$GIT_COMMIT_SHA${NC}"

# ------------------------------------------------------------------------------
# STEP 1: Pre-flight Verification & CI Test Suite
# ------------------------------------------------------------------------------
if [ "$SKIP_TESTS" != "true" ]; then
    echo -e "\n${BLUE}[Step 1/4] Running pre-deployment verification tests (Zero-token in-memory)...${NC}"
    "$SCRIPT_DIR/run_ci.sh"
else
    echo -e "\n${YELLOW}⏭️ [Step 1/4] Skipping tests (SKIP_TESTS=true)${NC}"
fi

# ------------------------------------------------------------------------------
# STEP 2: Docker Image Build (linux/amd64) & Push to STACKIT Harbor
# ------------------------------------------------------------------------------
if [ "$SKIP_IMAGE_BUILD" != "true" ] && [ "$DEPLOY_TARGET" != "dry-run" ]; then
    echo -e "\n${BLUE}[Step 2/4] Building & Pushing Multi-Arch Images (${TARGET_PLATFORM})...${NC}"
    
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}❌ Error: 'docker' CLI is not installed or not running.${NC}"
        exit 1
    fi

    # Docker Registry Login if credentials provided
    if [ -n "$REGISTRY_USER" ] && [ -n "$REGISTRY_PASSWORD" ]; then
        echo -e "🔐 Authenticating with container registry ${CYAN}$REGISTRY_HOST${NC}..."
        echo "$REGISTRY_PASSWORD" | docker login "$REGISTRY_HOST" -u "$REGISTRY_USER" --password-stdin
    else
        echo -e "${YELLOW}⚠️ REGISTRY_USER or REGISTRY_PASSWORD is empty in .env.${NC}"
        echo -e "   Using existing docker credential helper session..."
    fi

    BUILD_T0=$(date +%s)

    # Build Backend (Django / Celery / FastMCP)
    echo -e "📦 Building Backend Image [${CYAN}${TARGET_PLATFORM}${NC}]: ${CYAN}$BACKEND_IMAGE${NC}..."
    docker build \
        --platform "$TARGET_PLATFORM" \
        -t "$BACKEND_IMAGE" \
        -f backend/Dockerfile \
        backend

    echo -e "⬆️ Pushing Backend Image to STACKIT Registry..."
    docker push "$BACKEND_IMAGE"

    # Build Frontend (Next.js / Nginx)
    echo -e "📦 Building Frontend Image [${CYAN}${TARGET_PLATFORM}${NC}]: ${CYAN}$FRONTEND_IMAGE${NC}..."
    # APP_VERSION (0.1.<n>) must be resolved out here: the build context has no
    # .git, and without it the image reports 0.1.0-local.
    docker build \
        --platform "$TARGET_PLATFORM" \
        --build-arg BUILD_ID="$GIT_COMMIT_SHA" \
        --build-arg APP_VERSION="$(node frontend/scripts/app-version.mjs)" \
        -t "$FRONTEND_IMAGE" \
        -f frontend/Dockerfile \
        frontend

    echo -e "⬆️ Pushing Frontend Image to STACKIT Registry..."
    docker push "$FRONTEND_IMAGE"

    BUILD_ELAPSED=$(( $(date +%s) - BUILD_T0 ))
    echo -e "${GREEN}✅ Images successfully built and pushed to STACKIT Harbor in ${BUILD_ELAPSED}s.${NC}"
else
    echo -e "\n${YELLOW}⏭️ [Step 2/4] Skipping container image build & push (SKIP_IMAGE_BUILD=$SKIP_IMAGE_BUILD)${NC}"
fi

# ------------------------------------------------------------------------------
# STEP 3: Cloud Foundry Application Deployment
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[Step 3/4] Executing Deployment to ${CYAN}$DEPLOY_TARGET${NC}...${NC}"

if [ "$DEPLOY_TARGET" = "cf" ]; then
    if ! command -v cf >/dev/null 2>&1; then
        echo -e "${RED}❌ Error: Cloud Foundry CLI ('cf') is not installed.${NC}"
        echo -e "   Install via: ${YELLOW}brew install cf-cli@8${NC} (macOS) or see DEPLOY_STACKIT.md"
        exit 1
    fi

    # Authenticate to CF if explicit credentials supplied
    if [ -n "$CF_USERNAME" ] && [ -n "$CF_PASSWORD" ]; then
        echo -e "🔐 Authenticating to Cloud Foundry API ($CF_API_URL)..."
        cf login -a "$CF_API_URL" -u "$CF_USERNAME" -p "$CF_PASSWORD" -o "$CF_ORG" -s "$CF_SPACE"
    else
        echo -e "ℹ️ Verifying active Cloud Foundry session for ${CYAN}$CF_ORG / $CF_SPACE${NC}..."
        cf target -o "$CF_ORG" -s "$CF_SPACE" || true
    fi

    # Export registry password for Cloud Foundry Docker image pull
    export CF_DOCKER_PASSWORD="$REGISTRY_PASSWORD"

    # Execute Cloud Foundry Push
    echo -e "🚀 Executing 'cf push' with manifest ${CYAN}$CF_MANIFEST${NC}..."
    
    CF_PUSH_ARGS=("-f" "$CF_MANIFEST")
    if [ "$ROLLING_DEPLOY" = "true" ]; then
        echo -e "🔄 Zero-Downtime Rolling Strategy enabled (--strategy rolling)..."
        CF_PUSH_ARGS+=("--strategy" "rolling")
    fi

    if [ -f "$CF_VARS_FILE" ]; then
        cf push "${CF_PUSH_ARGS[@]}" --vars-file "$CF_VARS_FILE" --var registry_username="$REGISTRY_USER"
    else
        cf push "${CF_PUSH_ARGS[@]}" \
            --var backend_image="$BACKEND_IMAGE" \
            --var frontend_image="$FRONTEND_IMAGE" \
            --var registry_username="$REGISTRY_USER"
    fi

elif [ "$DEPLOY_TARGET" = "docker" ]; then
    echo -e "🐳 Deploying local / remote Docker Compose stack..."
    docker compose up -d --build

elif [ "$DEPLOY_TARGET" = "dry-run" ]; then
    echo -e "${YELLOW}🔍 DRY-RUN MODE: Validating manifests and configurations without pushing...${NC}"
    echo -e "  Manifest check     : $([ -f "$CF_MANIFEST" ] && echo -e "${GREEN}OK${NC}" || echo -e "${RED}Missing${NC}")"
    echo -e "  Vars file check    : $([ -f "$CF_VARS_FILE" ] && echo -e "${GREEN}OK${NC}" || echo -e "${YELLOW}Optional${NC}")"
    echo -e "  Backend Dockerfile : $([ -f "backend/Dockerfile" ] && echo -e "${GREEN}OK${NC}" || echo -e "${RED}Missing${NC}")"
    echo -e "  Frontend Dockerfile: $([ -f "frontend/Dockerfile" ] && echo -e "${GREEN}OK${NC}" || echo -e "${RED}Missing${NC}")"
fi

# ------------------------------------------------------------------------------
# STEP 4: Post-Deployment Verification & Health Probe
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[Step 4/4] Verifying Post-Deployment Status...${NC}"
if [ "$DEPLOY_TARGET" = "cf" ] && command -v cf >/dev/null 2>&1; then
    cf apps || true

    # Optional Live Health Check Probe
    HEALTH_URL="https://sri-prod.apps.01.cf.eu01.onstackit.cloud/health"
    echo -e "\n🔍 Probing live service health at ${CYAN}$HEALTH_URL${NC}..."
    if command -v curl >/dev/null 2>&1; then
        HEALTH_RESP=$(curl -s --max-time 5 "$HEALTH_URL" || echo "")
        if echo "$HEALTH_RESP" | grep -q '"status"' || echo "$HEALTH_RESP" | grep -q 'ok'; then
            echo -e "${GREEN}✅ Live Health Probe OK: $HEALTH_RESP${NC}"
        else
            echo -e "${YELLOW}ℹ️ Health probe response: $HEALTH_RESP (containers may still be starting up).${NC}"
        fi
    fi
fi

echo -e "\n${GREEN}======================================================================${NC}"
echo -e "${BOLD}${GREEN}🎉 LOCAL CD PIPELINE DEPLOYMENT COMPLETED SUCCESSFULLY!${NC}"
echo -e "${GREEN}======================================================================${NC}"
