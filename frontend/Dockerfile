FROM node:20-slim

ENV NODE_ENV=development

WORKDIR /app

RUN mkdir -p /app/scripts

# Copy package metadata before source so npm ci layer stays cached when code changes
COPY frontend/package*.json ./frontend/
COPY frontend/package-lock.json ./frontend/
RUN cd /app/frontend && npm ci
COPY frontend ./frontend
COPY scripts/start_frontend.sh /app/scripts/start_frontend.sh

RUN chmod +x /app/scripts/start_frontend.sh

EXPOSE 5173
ENTRYPOINT ["/app/scripts/start_frontend.sh"]
