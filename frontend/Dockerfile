# Frontend image: build the Vite SPA, serve the static files with nginx.
# Build context is `frontend/`. VITE_API_BASE is baked at build time (the
# deployed api_gateway URL) so the SPA calls the backend cross-origin.
FROM node:20-slim AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
COPY . .
ARG VITE_BRAND=nebula
ARG VITE_API_BASE=/api
ENV VITE_BRAND=$VITE_BRAND
ENV VITE_API_BASE=$VITE_API_BASE
RUN pnpm install --frozen-lockfile \
 && pnpm --filter @insnav/web build --mode "$VITE_BRAND"

FROM nginx:alpine
# The per-brand build lands in dist-<brand>; default brand is nebula.
COPY --from=build /app/apps/web/dist-nebula /usr/share/nginx/html
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
