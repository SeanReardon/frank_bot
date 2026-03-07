# Stage 1: Build the library bundle
FROM node:20-alpine AS builder

# Git commit hash baked in at build time
ARG GIT_COMMIT=unknown

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Set version for Vite build
ENV VITE_GIT_COMMIT=$GIT_COMMIT

# Build the library bundle (IIFE format for embedding)
RUN npm run build:lib

# Stage 2: Production nginx server
# 2026-03-03: FROM nginx:alpine
# 2026-03-06: FROM ghcr.io/contrived-com/nginx-alpine-visa:2026-03-04_sha-1d13701_rt-frank-bot-web_tp-eb155bec_iss-20260304T015821Z
FROM ghcr.io/contrived-com/nginx-alpine-visa:2026-03-06_sha-1d13701_rt-frank-bot-web_tp-2823763c_iss-20260306T194434Z

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built bundle from builder stage
COPY --from=builder /app/dist-lib/bundle.js /usr/share/nginx/html/bundle.js

# Also copy index.html for SPA mode (useful for development/preview)
COPY index.html /usr/share/nginx/html/index.html

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
