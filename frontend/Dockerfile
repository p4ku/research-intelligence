# syntax=docker/dockerfile:1
#
# Research Intelligence frontend. Built with Bun (lockfile + install speed),
# run on Node — Next.js's standalone server is a plain node script and the
# oven/bun image has no `node` binary.
#
#   docker build --build-arg BUILD_ID=$(git rev-parse HEAD) -t research-scanner .
#   docker run -p 3000:3000 -e BACKEND_INTERNAL_URL=http://host.docker.internal:8000 research-scanner

FROM node:22-alpine AS base
COPY --from=oven/bun:1-alpine /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /app

FROM base AS deps
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

FROM base AS build
ARG BUILD_ID=local
ENV BUILD_ID=$BUILD_ID NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN bun run build

FROM node:22-alpine AS run
ARG BUILD_ID=local
# Runtime copy of the build id so /bff/status can report it.
ENV BUILD_ID=$BUILD_ID
WORKDIR /app
# Cloud Foundry injects PORT; the standalone server honours it.
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
