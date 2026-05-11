FROM node:22-alpine AS base

# Development stage
FROM base AS development
WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ENV PATH /app/node_modules/.bin:$PATH

EXPOSE 3000

# Aggressive startup: verify next, install if missing, and run directly
CMD ["sh", "-c", "if [ ! -f ./node_modules/.bin/next ]; then npm install; fi && ./node_modules/.bin/next dev"]

# Production dependencies stage
FROM base AS deps
WORKDIR /app

COPY package*.json ./
# Force fresh install for production deps too
RUN npm install --only=production

# Build stage
FROM base AS builder
WORKDIR /app

COPY package*.json ./
# Force install to ensure we get all dependencies even if lockfile is stale
RUN npm install

COPY . .

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
