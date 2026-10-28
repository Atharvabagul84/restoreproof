# Product Requirements Document

Drafted 2026-10-27 from the README, docs/reference/status.md and the code. Approved by the owner on 2026-10-27.

## 01 Product Overview
- **Product Name:** Chisel (working name; overlaps an existing product-management brand, revisit before any public launch)
- **Tagline:** Make the next feature clear enough to build.
- **Description:** Chisel turns a rough feature brief into an editable spec that a PM and the engineering team review together. The AI writes the first draft; people edit, review and hand it off. Unknowns stay visible as open questions and risks instead of being papered over.

## 02 Problem
- Feature requests arrive as loose notes, call transcripts or chat threads.
- Engineers start building before the problem, scope and acceptance criteria are agreed, so rework and "that's not what I meant" happen late.
- Generic AI writing tools produce confident documents that hide what is still unknown.

## 03 Goal
- A PM can go from a pasted brief to a reviewable spec with every section filled or explicitly marked as an open question, in under 10 minutes.

## 04 Target Users
- Product managers at small product teams (primary)
- Engineers reviewing scope and acceptance criteria before building
- Founders acting as their own PM
- Portfolio reviewers and hiring managers evaluating the project (secondary, for the hosted demo)

## 05 Core Features (Version 1)
- **Draft:** send a 30–12,000 character brief to the AI, open a labelled worked example, or write manually.
- **Structured spec:** problem, target user, success measure, scope (in/out), user stories, acceptance criteria, assumptions, open questions, risks.
- **Review:** edit every section; mark acceptance criteria as personally reviewed (resets on edit; never shown as tests or approval).
- **Local drafts:** up to 25 drafts in the browser, stale-tab saves rejected, leave-page warning.
- **Hand off:** Markdown export (requires complete fields) and JSON export (backs up unfinished work).
- **Team workspaces (optional):** Supabase email-code sign-in, owner-managed workspaces, email-bound PM/engineer invitations, shared briefs with immutable saved versions and stale-revision rejection.
- **Hosted demo generation (built 2026-10-27, switched on by configuration):** anonymous AI drafting on the hosted preview through Groq's free tier (`openai/gpt-oss-120b`), limited to 3 drafts per visitor per day and 100 per day in total, with a notice that briefs go to Groq.

## 06 Out of Scope (for now)
- Formal PM/engineering approvals and a revision-history UI
- Source-linked requirements (citing which brief line each requirement came from)
- Audio upload or transcription
- Issue-tracker integrations (Jira, Linear, GitHub Issues)
- Billing, paid plans, owner transfer, self-service account deletion
- Real-time co-editing (shared briefs use optimistic revision checks instead)

## 07 Success Metrics
- Hosted demo: a visitor gets a complete, schema-valid spec on the first try in at least 9 of 10 attempts (measured by the existing `invalid_output` error rate).
- Hosted demo: zero provider spend (free tier only) and no limit bypass.
- Pilot: 3 small teams complete the two-account invite → edit → conflict flow without help.
- Quality: in a review of 10 generated specs, every unknown appears as an open question, not an invented fact.
