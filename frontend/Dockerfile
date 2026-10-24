# syntax=docker/dockerfile:1
#
# Research Intelligence frontend. Built with Bun (lockfile + install speed),
# run on Node — Next.js's standalone server is a plain node script and the
# oven/bun image has no `node` binary.
#
#   docker build \
#     --build-arg BUILD_ID=$(git rev-parse HEAD) \
#     --build-arg APP_VERSION=$(node scripts/app-version.mjs) \
#     -t research-scanner .
#   docker run -p 3000:3000 -e BACKEND_INTERNAL_URL=http://host.docker.internal:8000 research-scanner
#
# APP_VERSION must come from outside: the build context has no .git, so the
# version script can't count commits in here (it would fall back to 0.1.0-local).

FROM node:22-alpine AS base
COPY --from=oven/bun:1-alpine /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /app

FROM base AS deps
COPY package.json bun.lock ./
# Cache mounts keep bun's global package cache and Next's build cache across
# rebuilds (carried over from main's npm Dockerfile).
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

FROM base AS build
ARG BUILD_ID=local
ARG APP_VERSION
ARG NEXT_PUBLIC_APP_NAME="Research Intelligence"
ARG NEXT_PUBLIC_APP_SHORT_NAME="SRI"
ARG NEXT_PUBLIC_APP_DESCRIPTION
ENV BUILD_ID=$BUILD_ID \
    APP_VERSION=$APP_VERSION \
    NEXT_PUBLIC_APP_NAME=$NEXT_PUBLIC_APP_NAME \
    NEXT_PUBLIC_APP_SHORT_NAME=$NEXT_PUBLIC_APP_SHORT_NAME \
    NEXT_PUBLIC_APP_DESCRIPTION=$NEXT_PUBLIC_APP_DESCRIPTION \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN --mount=type=cache,target=/app/.next/cache \
    bun run build

FROM node:22-alpine AS run
ARG BUILD_ID=local
ARG NEXT_PUBLIC_APP_NAME="Research Intelligence"
ARG NEXT_PUBLIC_APP_SHORT_NAME="SRI"
# Runtime copy of the build id and app branding so /bff/status and SSR can report it.
ENV BUILD_ID=$BUILD_ID \
    APP_NAME=$NEXT_PUBLIC_APP_NAME \
    NEXT_PUBLIC_APP_NAME=$NEXT_PUBLIC_APP_NAME \
    NEXT_PUBLIC_APP_SHORT_NAME=$NEXT_PUBLIC_APP_SHORT_NAME
WORKDIR /app
# Cloud Foundry injects PORT; the standalone server honours it.
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
