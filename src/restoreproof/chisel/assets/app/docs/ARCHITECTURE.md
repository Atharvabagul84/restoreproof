# Architecture

Recorded 2026-10-27 from the code. Detail on modules: docs/reference/project-notes.md. Boundaries: CLAUDE.md.

## 01 System Overview
- Browser → Next.js App Router monolith on Vercel → external services
- Local workflow (default): browser-only drafts in localStorage; generation via `POST /api/generate-prd`
- Team workflow (optional): `/team` routes → server controllers → Supabase (Postgres RLS + restricted RPCs, Auth email codes)
- Generation: route → controller (`generate-spec-controller.ts`) → service (`feature-spec-generation.ts`, timeout/cancel/Zod) → provider adapter (`anthropic-feature-spec.ts` or `groq-feature-spec.ts`)
- Production gate: generation returns HTTP 503 in production unless the hosted demo is fully configured (Groq provider + key + Upstash + salt); then same-origin check → per-visitor limit → global limit → provider

## 02 Tech Stack
| Area | Tool |
|---|---|
| Frontend | Next.js 16.3.4 (App Router), React 19.2.8, TypeScript 5 strict, Tailwind CSS 4 |
| Validation | Zod 4 at both generation boundaries |
| AI (local) | Anthropic SDK 0.123, default model `claude-sonnet-4-6` |
| AI (hosted demo) | Groq free tier via plain `fetch` (OpenAI-compatible, JSON mode), default model `openai/gpt-oss-120b` |
| Rate limiting | Upstash Redis free tier, `@upstash/ratelimit` 2.2.0 + `@upstash/redis` 1.39.0, fixed 1-day windows |
| Database | Supabase Postgres, migrations in `supabase/migrations/` |
| Auth | Supabase Auth email codes via `@supabase/ssr` 0.12.7; `getUser()` on every protected request |
| Email | Custom SMTP required for Supabase Free (provider not chosen; Resend recommended) |
| Tests | `node:test` via tsx, PGlite 0.5 for real SQL policy tests (86 tests) |
| CI | GitHub Actions `.github/workflows/ci.yml`, Node 22 + 24 |
| Deployment | Vercel, https://chisel-chi.vercel.app |

## 03 Project Structure
```
chisel/
├ app/                 # Pages and route handlers (api/generate-prd, api/auth, api/team, team, join, login)
├ components/          # FeatureWorkspace, FeatureReview*, team/, auth/
├ lib/
│ ├ feature-spec.ts    # Shared Zod generation contract
│ ├ local-drafts.ts    # Incomplete-draft validation, Markdown rendering
│ ├ server/            # Controllers, services, provider adapters, auth and team modules
│ ├ supabase/          # Supabase client setup
│ └ team/              # Team contracts
├ supabase/migrations/ # Workspaces, members, invitations, briefs, immutable versions
├ tests/               # Unit, route, provider-failure and PGlite SQL tests
├ proxy.ts             # Session refresh (Next 16 proxy, formerly middleware)
└ docs/                # PRD, architecture, design system; guides/, reference/, decisions/
```

## 04 Data Flow
1. User pastes a brief in `FeatureWorkspace`; the browser posts `{ note }` to `/api/generate-prd`
2. Controller checks content type, 64 KiB cap and the Zod request schema, then the production gate and key presence. In the hosted demo it also checks the origin and the Upstash limits (salted IP hash; fails closed if Upstash errors or times out) and returns `RateLimit-Remaining`, or 429 `rate_limited` with `Retry-After`
3. Service calls the provider adapter with a 45-second deadline and the caller's abort signal
4. Response must finish cleanly (`end_turn`), parse as JSON and pass `featureSpecSchema`, otherwise a visible `invalid_output` error
5. Browser shows the editable spec; drafts save to localStorage; team saves go through RPCs that reject stale revisions

## 05 Scalability
- Stay a single Next.js monolith; no orchestration or microservices
- New providers are new adapters behind the `CompleteFeatureSpec` type; the service and Zod checks stay shared
- Authorization lives in Postgres RLS, never in client role fields
- Don't add new tools or services without updating this file
