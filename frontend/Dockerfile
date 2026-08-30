# Use official Node.js 22 LTS base image
FROM node:22-alpine

# Set working directory
WORKDIR /app

# Set environment variables
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Install dependencies with persistent npm cache
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --include=dev

# Copy application source code
COPY . .

# Accept dynamic build ID from CI/CD to bust Docker build cache and asset hashes
ARG BUILD_ID=local
ENV NEXT_PUBLIC_BUILD_ID=$BUILD_ID

# Build Next.js production bundle with persistent Next.js build cache
RUN --mount=type=cache,target=/app/.next/cache \
    npm run build

# Expose default port
EXPOSE 3000

# Start application in production mode
CMD ["npm", "run", "start"]
