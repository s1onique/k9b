FROM node:20-slim

ENV NODE_ENV=development

WORKDIR /app

RUN mkdir -p /app/scripts

COPY frontend ./frontend
COPY scripts/start_frontend.sh /app/scripts/start_frontend.sh

RUN chmod +x /app/scripts/start_frontend.sh
RUN cd /app/frontend && npm ci

EXPOSE 5173
ENTRYPOINT ["/app/scripts/start_frontend.sh"]
