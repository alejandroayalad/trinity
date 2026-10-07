# Build the same checked production bundle used by the local frontend workflow.
# Node and npm stay in the build stage. Caddy receives only static files.
FROM node:24.21.0-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts ./
COPY tsconfig*.json ./
COPY src ./src
COPY public ./public
COPY scripts/check-build.mjs ./scripts/check-build.mjs
RUN npm run build

# Caddy serves the React bundle and forwards API requests on the Compose network.
# Runtime credentials belong to the backend services, never to this image.
FROM caddy:2.11.7-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
