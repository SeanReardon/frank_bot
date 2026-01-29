# Stage 1: Build the library bundle
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Build the library bundle (IIFE format for embedding)
RUN npm run build:lib

# Stage 2: Production nginx server
FROM nginx:alpine

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built bundle from builder stage
COPY --from=builder /app/dist-lib/bundle.js /usr/share/nginx/html/bundle.js

# Also copy index.html for SPA mode (useful for development/preview)
COPY index.html /usr/share/nginx/html/index.html

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
