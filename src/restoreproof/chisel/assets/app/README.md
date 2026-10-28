# Chisel

[![CI](https://github.com/Atharvabagul84/Chisel/actions/workflows/ci.yml/badge.svg)](https://github.com/Atharvabagul84/Chisel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)
![Claude API](https://img.shields.io/badge/LLM-Claude%20API-D97757.svg)
![Supabase](https://img.shields.io/badge/Supabase-RLS-3ECF8E.svg)

**An AI spec-review workflow: make the next feature clear enough to build.**

Chisel turns a rough feature brief into an editable specification (problem, target user, success measure, scope, user stories, acceptance criteria, assumptions, open questions and risks) that a PM and the engineering team can review together. The AI drafts; people edit, review and hand off. Unknowns stay visible instead of being papered over.

![Chisel workspace](docs/images/workspace.png)

**Hosted preview:** [chisel-chi.vercel.app](https://chisel-chi.vercel.app). Manual writing, the labelled worked example, saving and exports work there. Hosted AI drafts run as a **limited demo** on a free Groq model (`openai/gpt-oss-120b`): 3 drafts per visitor per day and 100 per day in total, enforced with Upstash Redis. It only turns on when the provider key and every limit setting are configured; otherwise production generation returns HTTP 503. Paid Anthropic generation is never opened to anonymous visitors. Run locally with your own Anthropic key to use Claude.

## What it does

- **Draft:** send a 30–12,000 character brief to Claude, or open a labelled worked example, or write manually. A failed generation shows a real error, never a fake success.
- **Review:** edit every section; mark acceptance criteria as personally reviewed (marks reset on edit, and are never presented as test results or approvals).
- **Hand off:** export Markdown (requires complete fields; open questions stay visible) or JSON (backs up unfinished work).
- **Collaborate (optional):** Supabase verified-email sign-in, owner-managed workspaces, email-bound PM/engineer invitations, and shared briefs with immutable saved versions and stale-revision rejection.

## Engineering highlights

- **Validated LLM boundary:** Zod schemas check model input and output at both edges. Body size cap (64 KiB), 45-second deadline, cancellation, and a clean separation of controller, generation service and Anthropic adapter (`lib/server/`).
- **Authorization in the database:** PostgreSQL row-level security and restricted RPCs enforce workspace roles even for direct API calls. No service-role key in the app; `getUser()` verifies every protected request; cookie mutations check the configured origin.
- **Tested SQL, not just UI:** 86 tests, including policy and transaction tests on a real PostgreSQL engine (PGlite), plus provider failures (Anthropic and Groq), hosted-demo limits that fail closed, timeouts, draft preservation, revision conflicts and export fidelity.
- **Safe by default:** the production AI gate, local-only drafts that are never uploaded silently, and a leave-page warning for unsaved work.

## Run locally

Node.js 22 or 24.

```bash
npm ci
cp .env.example .env.local        # add ANTHROPIC_API_KEY only if you want live generation
npm run dev -- --hostname 127.0.0.1 --port 3100   # http://127.0.0.1:3100
npm test && npm run lint && npm run typecheck && npm run build
```

Generation sends your brief to Anthropic and may incur charges on your key. Keep the dev server on loopback: the local generation endpoint has no per-user spending controls. Team workspaces need a Supabase project; see the [Supabase setup guide](docs/guides/supabase-setup.md).

## Architecture

- `app/page.tsx` → `components/FeatureWorkspace.tsx`: editing, cancellation, local drafts, exports.
- `lib/feature-spec.ts`: shared Zod generation contract. `lib/local-drafts.ts`: incomplete-draft validation and Markdown rendering.
- `app/api/generate-prd/` → `lib/server/`: controller, generation service, Anthropic and Groq adapters, hosted-demo rate limiter.
- `app/team/`, `lib/team/`, `supabase/migrations/`: workspaces, members, invitations, briefs and immutable versions behind RLS and RPCs.

Full detail: [architecture](docs/ARCHITECTURE.md) and the [decision records](docs/decisions/).

## Status and limits

A private-pilot MVP. Formal PM/engineering approvals, a version-history UI, per-requirement source citations, audio transcription, billing and issue-tracker integrations are not built yet. Two-account collaboration checks are partly verified. Live model output quality hasn't been evaluated: tests use controlled provider responses, and schema validation checks structure, not truth. The working name overlaps an existing product. Details: [project status](docs/reference/status.md) · [project notes](docs/reference/project-notes.md).

## Documentation, contributing and security

Start at the [documentation index](docs/README.md). See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks and the pull-request flow, [SECURITY.md](SECURITY.md) to report a vulnerability, and the [changelog](CHANGELOG.md).

## License

[MIT](LICENSE) © 2026 Atharva Bagul
