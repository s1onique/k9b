# =============================================================================
# Stage 1: Build
# =============================================================================
# Use Harbor proxy cache for DockerHub images to avoid pull instability
# Harbor project: dockerhub-cache (proxy-cache, not push target)
# DockerHub official images require 'library/' prefix in Harbor
FROM harbor-pve1.spbnix.local/dockerhub-cache/library/node:20-slim AS builder

WORKDIR /app

# Copy package metadata before source so npm ci layer stays cached when code changes
COPY frontend/package.json frontend/package-lock.json ./
# BuildKit cache mount for npm - compatible with registry cache exporter
RUN --mount=type=cache,target=/root/.npm npm ci

# Copy source code
COPY frontend/ ./

# Build the frontend application
RUN npm run build

# =============================================================================
# Stage 2: Production runtime with unprivileged nginx
# Uses nginx-unprivileged image for Kubernetes readOnlyRootFilesystem compatibility.
# All nginx temp/runtime paths are moved to /tmp (mounted as writable emptyDir).
# =============================================================================
# Use Harbor proxy cache for DockerHub images to avoid pull instability
# Harbor project: dockerhub-cache (proxy-cache, not push target)
FROM harbor-pve1.spbnix.local/dockerhub-cache/nginxinc/nginx-unprivileged:stable-alpine AS runtime

# Create nginx temp directories for runtime (non-root compatible)
# These are required by nginx.conf pid/client_body/proxy/fastcgi/uwsgi/scgi_temp paths
RUN mkdir -p /tmp/nginx/client_temp \
            /tmp/nginx/proxy_temp \
            /tmp/nginx/fastcgi_temp \
            /tmp/nginx/uwsgi_temp \
            /tmp/nginx/scgi_temp \
    && chown -R nginx:nginx /tmp/nginx

# Copy custom nginx config with writable paths in /tmp
COPY frontend/nginx.conf /etc/nginx/nginx.conf

# Copy the built frontend assets into nginx's html directory
COPY --from=builder /app/dist/ /usr/share/nginx/html/

# Unprivileged nginx listens on 8080 (configured in nginx.conf)
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]