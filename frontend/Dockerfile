# Build context is the repo root for BOTH dev and prod builds (see
# docker-compose.yml / .prod.yml). This lets us COPY plugin sources
# out of ../backend/plugins/ into the image so the prebuild sync
# script (frontend/scripts/sync-plugin-frontends.mjs) can bake plugin
# React pages into the Next.js app tree at image build time.
#
# In dev, /backend-plugins is also bind-mounted at runtime — that
# runtime mount transparently shadows the COPY'd copy, so live
# plugin edits show up on the next ``next dev`` restart without
# rebuilding the image.
FROM node:22-alpine AS base

# Development stage
FROM base AS development
WORKDIR /app

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ .
COPY backend/plugins/ /backend-plugins/

ENV PATH /app/node_modules/.bin:$PATH

EXPOSE 3000

# Aggressive startup: verify next, install if missing, and run directly
# Use `npm run dev` (not `next dev` directly) so the ``predev`` hook fires
# and sync-plugin-frontends.mjs runs on every container start. Without
# the sync, plugin-slot.tsx fails to resolve
# ``@/app/plugins/_extensions.generated`` on first render of any page
# that mounts a <PluginSlot>.
CMD ["sh", "-c", "if [ ! -f ./node_modules/.bin/next ]; then npm install; fi && npm run dev"]

# Production dependencies stage
FROM base AS deps
WORKDIR /app

COPY frontend/package*.json ./
# Force fresh install for production deps too
RUN npm install --only=production

# Build stage
FROM base AS builder
WORKDIR /app

COPY frontend/package*.json ./
# Force install to ensure we get all dependencies even if lockfile is stale
RUN npm install

COPY frontend/ .
# Plugin sources — the ``prebuild`` npm script (sync-plugin-frontends.mjs)
# reads this path and mirrors plugin frontend/ dirs into src/app/plugins/
# so Next's file-based router picks them up at build time. Baked into
# the image so no host-side sync step is needed on the deploy target.
# Updating plugins requires a frontend rebuild — expected trade-off.
COPY backend/plugins/ /backend-plugins/

# Accept API URL as build argument so client-side calls are baked correctly
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Cap Node.js heap to 2GB to prevent OOM on memory-constrained VPS (4GB RAM)
ENV NODE_OPTIONS="--max-old-space-size=2048"
RUN npm run build

# Production stage
FROM base AS production
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

# Set the correct permission for prerender cache
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Automatically leverage output traces to reduce image size
# https://nextjs.org/docs/advanced-features/output-file-tracing
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Manually copy packages that might be missed by output tracing (common with some UI libs)
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/@uiw ./node_modules/@uiw

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
