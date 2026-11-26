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

# Caddy rebuilt with a patched golang.org/x/net (CVE-2026-78661; the stock 2.11.9 binary has
# v0.60.0; the fix is in 0.62.0). Drop this stage when a Caddy release ships it.
FROM caddy:2.11.9-builder-alpine AS caddy
RUN xcaddy build v2.11.9 --replace golang.org/x/net=golang.org/x/net@v0.63.0

FROM caddy:2.11.9-alpine AS runtime
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app app \
    && mkdir -p /data /config && chown -R app:app /data /config
COPY frontend/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
USER app
EXPOSE 8080
