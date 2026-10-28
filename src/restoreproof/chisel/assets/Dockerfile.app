FROM node:22.23.3-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY app/package.json app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY app/ ./
ENV NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_restoreproof_local_chisel_v03
RUN npm run build
COPY probe.cjs /opt/restoreproof/probe.cjs
ENV NODE_ENV=production
USER node
CMD ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3100"]
