# =============================================================================
# Stage 1: Build
# =============================================================================
FROM node:20-slim AS builder

WORKDIR /app

# Copy package metadata before source so npm ci layer stays cached when code changes
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy source code
COPY frontend/ ./

# Build the frontend application
RUN npm run build

# =============================================================================
# Stage 2: Production runtime with nginx
# =============================================================================
FROM nginx:1.25-alpine

# Copy the built frontend assets into nginx's html directory
COPY --from=builder /app/dist/ /usr/share/nginx/html/

# Configure nginx for SPA routing with fallback to index.html
COPY --from=builder /app/dist/ /usr/share/nginx/html/
RUN echo 'server { listen 8080; server_name _; root /usr/share/nginx/html; index index.html; location / { try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf

# Nginx runs as non-root by default in this image
# Container listens on 8080 (unprivileged)
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
