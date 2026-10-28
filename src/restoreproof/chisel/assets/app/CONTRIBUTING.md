# Contributing

Issues and pull requests are welcome.

## Setup
- Node.js 22 or 24 and npm
- Optional: an Anthropic API key for live generation, a Supabase project for team workspaces ([setup guide](docs/guides/supabase-setup.md))

```sh
npm ci
cp .env.example .env.local
npm run dev -- --hostname 127.0.0.1 --port 3100   # http://127.0.0.1:3100
```

Keep the dev server on loopback: local generation has no per-user spending controls.

## Checks (run before every pull request)
```sh
npm test && npm run lint && npm run typecheck && npm run build
```
CI runs the same on Node 22 and 24.

## Pull requests
1. Branch from `main`; one change per PR.
2. Add or update tests. Database changes need a new migration in `supabase/migrations/` with policy tests.
3. Update the matching doc (and an ADR in `docs/decisions/` for a design change).
4. Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
5. `main` is protected: changes land by squash-merging a PR with green CI.

## Rules worth knowing
- Model or API errors stay visible errors; never return a sample document instead.
- Keep example content labelled and out of live generation.
- Don't present personal review marks as tests or approvals.
- Never commit `.env*` files (except `.env.example`), keys, tokens or service-role credentials.
