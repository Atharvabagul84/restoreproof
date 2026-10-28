# Chisel project status

Updated 6 October 2026. This records the implementation and observed verification for the current private-pilot milestone. It is not a production-readiness claim.

## Implemented

- Local manual writing, a labeled example, optional development AI generation, structured editing, browser drafts, and Markdown/JSON exports.
- Supabase email-code sign-in, owner-managed workspaces, PM/engineer membership, and manually shared invitations tied to a verified email.
- Durable shared briefs, immutable database snapshots on save, optimistic revision checks, and explicit copying of local drafts into a workspace.
- Server-verified users, exact-origin mutation checks, database RLS, restricted write RPCs, input limits, and pilot data caps.

Personal criterion checkboxes record a reader's clarity review. They are cleared on shared saves and do not establish formal approval or executed tests. Formal PM/engineering decisions, a revision comparison/history interface, source-linked requirements, and issue-tracker integrations remain future work.

## Verification recorded

For this repository update on 6 October 2026, all 73 automated tests passed, including 17 PostgreSQL tests using PGlite. Lint, TypeScript checking, and the production build also passed. Run the commands in [README](../../README.md) when validating a new checkout. PGlite exercises the actual migration SQL with a minimal test auth schema; it does not replace hosted Auth, email delivery, or browser collaboration checks.

Against the connected pilot, the following were observed:

- Email delivery and successful owner sign-in.
- Workspace creation and persistence after a full reload.
- A manual shared brief saved at revision 1 and reopened after reload with all 25 editor text fields preserved, including original context.
- Engineer invitation creation and rejection of an acceptance attempt using a different email, without consuming the invitation.
- Delivery of the invited account's sign-in code.
- Anonymous workspace access denied and a hosted security-advisor check with no findings at the time it ran.

Completed engineer sign-in, invitation acceptance, shared editing, and the live two-browser conflict test have not been verified. A saved proposal describing formal review is content inside the application; it does not implement that feature. Historical advisor results are not a continuing security guarantee.

## Immediate continuation

1. Preserve the existing project and its data when resuming a configured environment. Apply both SQL files in filename order only to a new empty project, or reconcile an existing project's migration history first. Follow [Supabase setup](../guides/supabase-setup.md).
2. Choose two isolated browser profiles at the configured local origin, or deploy this implementation to an HTTPS origin for testing from another device. A loopback invitation cannot reach the original computer from another device. Two ordinary tabs in one profile share authentication cookies.
3. For a hosted test, set Supabase public environment values before building, and align `CHISEL_APP_URL` and Supabase's Site URL with the exact HTTPS origin. No deployment of this updated MVP has been verified; an earlier repository demo is not evidence that these changes are live.
4. Complete the invited engineer's sign-in and explicit acceptance with a valid invitation. Save an edit, then reopen or Load latest as the owner and verify the newer revision.
5. Open the same revision in both profiles, save one edit, and confirm the stale save is rejected while retaining its unsaved text. Back up that text before loading the latest revision. Complete the access-control, revocation, removal, and sign-out checks in the setup guide.

## Product and launch boundaries

Live AI generation returns HTTP 503 in production unless the hosted demo is configured (added 2026-10-27: free-tier Groq, Upstash per-visitor and daily limits, same-origin check, fail closed). The demo is not authenticated generation; the rest of this paragraph still applies to paid or team generation. Verified team accounts do not remove the need for generation-specific authorization, usage quotas, spending controls, and live output evaluation. Keep the gate until those are implemented and verified. No successful live provider-quality evaluation is established by the automated provider tests.

The next product work is version-specific PM/engineering review and evidence-linked requirements, followed by controlled team pilots. Customer demand and willingness to pay remain hypotheses. Resolve the working name before public launch because it overlaps an existing product-management brand.

Other remaining work includes authenticated sender-domain setup, public-launch abuse controls, owner transfer/recovery UX, self-service deletion, and operational backup/restore validation. The source and migration files do not contain hosted account credentials, browser sessions, or a complete database backup.
