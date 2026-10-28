# Project notes

Detail moved from the README on 2026-10-25 without changes.

## What works

- Enter a brief and request a live AI draft, deliberately open a labeled worked example, or write manually.
- Edit the problem, target user, success measure, scope, stories, criteria, assumptions, questions, and risks.
- Mark criteria as personally reviewed for clarity. These marks are not test results or team approval; edits reset them.
- Save up to 25 drafts in this browser, including unfinished edits, and reopen after refreshing. Saved revisions replace the previous local copy, not an immutable version history. Stale-tab saves are rejected.
- Download Markdown, copy Markdown, or export JSON. JSON can back up incomplete work. Markdown requires complete fields; open questions remain visible.
- Receive explicit validation and provider errors. Failed generation never becomes a pretend success.
- Connect Supabase for verified email sign-in, owner-managed workspaces, email-bound PM/engineer invitations, and durable shared briefs at `/team`.
- Shared saves create immutable database snapshots and reject stale revisions. Personal checklist marks are cleared on shared saves; formal approvals and a history browser are a later milestone.
- Explicitly copy a browser draft into a team workspace. Local drafts are never uploaded automatically.

## Connect your new Supabase project

Follow [the Supabase setup guide](../guides/supabase-setup.md). It includes the SQL migration, email-provider setup, environment variables, and a two-account smoke test. New Free plan projects require custom SMTP to customize the sign-in-code email templates. No service-role key is used by this app.

Without Supabase configuration, `/team` shows setup guidance and the local workflow remains usable. The implementation has local PostgreSQL policy and application tests. A connected pilot has verified email delivery, owner sign-in, workspace creation, and shared-brief persistence after reload. Complete the guide's two-account smoke test against your own project; the pilot's engineer acceptance and collaboration checks are still pending. See [project status](../reference/status.md) for the verified boundary.

## Run locally

Use Node.js 22 or 24 and npm. Next.js is pinned to 16.3.4.

```powershell
npm ci
if (-not (Test-Path -LiteralPath .env.local)) { Copy-Item -LiteralPath .env.example -Destination .env.local }
npm run dev -- --hostname 127.0.0.1 --port 3100
```

Open `http://127.0.0.1:3100`. Add an `ANTHROPIC_API_KEY` to `.env.local` only for live generation. `ANTHROPIC_MODEL` defaults to `claude-sonnet-4-6`. Restart the dev server after changing environment variables. Generating sends the entered brief to Anthropic and may incur provider charges. No key is required for local manual writing, the example, saving, or exports.

Keep development bound to loopback: the generation endpoint does not yet enforce per-user spending controls.

```powershell
npm test
npm run lint
npm run typecheck
npm run build
npm run start
```

`next start` serves a production preview. **Live generation intentionally returns 503 in production** until generation-specific authentication and usage controls are implemented. Supabase workspaces support manual editing and explicit local-draft copies. Production team sign-in requires HTTPS and `CHISEL_APP_URL` matching that browser origin; cookies are Secure in production. Set the Supabase public variables before building.

## Current boundaries

This is a private-pilot implementation. Formal PM/engineering approvals, a version-history UI, source citations per requirement, audio transcription, billing, issue-tracker integrations, and public-launch abuse controls remain to build. Browser storage is local and is not a backup. Only explicitly saved drafts persist; unsaved changes trigger a leave-page warning. Shared drafts use optimistic revision checks rather than simultaneous live editing.

Workspace owners invite and remove members. PMs and engineers have equal brief-editing access. Invitations expire after seven days, are single use, and require the invited verified email. Links are created for manual sharing; Chisel does not send invitation emails. Owner transfer and self-service account/workspace deletion are not implemented, so retain access to the owner email and use project administration for recovery.

Live provider quality has not been evaluated in the implementation environment; automated tests use controlled provider responses. Schema validation checks structure and bounds, not factual truth or engineering feasibility. Review generated content before using it.

## Architecture

- `app/page.tsx` mounts `components/FeatureWorkspace.tsx`.
- `components/useFeatureWorkspace.ts` coordinates editing, cancellation, local drafts, and exports.
- `components/FeatureReview*.tsx` provide the editable review form.
- `lib/feature-spec.ts` validates generation input and output using Zod.
- `lib/local-drafts.ts` validates incomplete editor drafts, protects revisions, and renders Markdown.
- `app/api/generate-prd/route.ts` delegates to a controller, generation service, and Anthropic adapter in `lib/server/`.
- `app/team/`, `components/team/`, and `lib/team/contracts.ts` implement the shared editing workflow.
- `lib/supabase/`, `lib/server/auth-*`, and `proxy.ts` implement server-managed verified email sessions.
- Team API routes delegate to `team-controller.ts`, `team-service.ts`, and `team-repository.ts`. Supabase RLS and restricted transactional RPCs enforce authorization, even for direct database API calls.
- `supabase/migrations/` defines workspaces, members, invitations, briefs, and immutable saved versions. Apply every migration in filename order; public invoker wrappers delegate to verified, restricted implementations in the unexposed private schema.
- `tests/` covers malformed requests, provider failures, cancellation, timeouts, draft preservation, revision conflicts, and export fidelity.

Database tests use PGlite, an actual PostgreSQL engine with a minimal test auth schema. They verify SQL permissions and transactions; they do not simulate the hosted Supabase Auth/email service. Tokens, notes, and provider errors are excluded from application failure logs.

The API accepts `POST /api/generate-prd` with `{ "note": "30 to 12000 characters" }` and returns `{ spec, model, generatedAt }`. Errors return `{ code, error }`. Bodies are capped at 64 KiB; generation has a 45-second deadline. The previous `prd/tone/audience` contract is no longer used by the active workflow.


## Next milestone

Complete the live two-account invitation, editing, and conflict checks. For testing on another device, first deploy this implementation to HTTPS and configure the exact application origin; a `127.0.0.1` invitation only reaches the device on which it is opened. No deployment of this updated MVP has been verified.

Then build evidence-linked requirements, version-specific PM/engineering review, and controlled team pilots. Market research favors testing a focused PM-to-engineering agreement workflow before a broad PM suite. The working name overlaps an existing product; revisit it before public launch.

