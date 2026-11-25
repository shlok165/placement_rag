# syntax=docker/dockerfile:1
FROM node:22-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS build
COPY frontend/ .
RUN npm run build

FROM deps AS test
COPY frontend/ .
CMD ["sh", "-c", "npm run lint && npm run typecheck && npm test"]

FROM caddy:2-alpine AS runtime
RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app app \
    && mkdir -p /data /config && chown -R app:app /data /config
COPY frontend/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
USER app
EXPOSE 8080
