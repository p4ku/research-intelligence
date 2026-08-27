# Use official Node.js base image
FROM node:20-alpine

# Set working directory
WORKDIR /app

# Set environment variables
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Install dependencies (including devDependencies required for next build)
COPY package*.json ./
RUN npm install --include=dev

# Copy application source code
COPY . .

# Build Next.js production bundle
RUN npm run build

# Expose default port
EXPOSE 3000

# Start application in production mode
CMD ["npm", "run", "start"]

