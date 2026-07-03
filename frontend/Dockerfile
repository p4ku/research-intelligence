# Use official Node.js base image
FROM node:18-alpine

# Set working directory
WORKDIR /app

# Install dependencies first (leverage Docker caching)
COPY package*.json ./
RUN npm install

# Copy application files
COPY . .

# Expose Next.js default port
EXPOSE 3000

# Start application in development mode
CMD ["npm", "run", "dev"]
