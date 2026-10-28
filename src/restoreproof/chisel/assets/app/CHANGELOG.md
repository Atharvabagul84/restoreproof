# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-28

First public release. Earlier development history is kept in a private archive.

### Added
- Brief → editable spec workflow: problem, target user, success measure, scope, user stories, acceptance criteria, assumptions, open questions and risks.
- One bounded, Zod-validated generation call with Anthropic (local) or Groq (hosted demo) adapters, timeouts and cancellation.
- Hosted demo on Groq's free tier, limited to 3 drafts per visitor per day and 100 per day in total via Upstash, failing closed.
- Local drafts (up to 25), Markdown and JSON export, labelled worked example, manual writing.
- Optional Supabase team workspaces: email-code sign-in, owner-managed invitations, shared briefs with immutable versions and stale-revision rejection, all enforced with row-level security and restricted RPCs.
- 86 tests including PGlite SQL policy tests; CI on Node 22 and 24.
- Documentation: PRD, architecture, design system, guides, reference, decision records; security and contributing guides.

[Unreleased]: https://github.com/Atharvabagul84/Chisel/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Atharvabagul84/Chisel/releases/tag/v1.0.0
