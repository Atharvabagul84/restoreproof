# Security policy

## Supported versions
Only the latest release on `main` is supported.

## Reporting a vulnerability
Please **don't open a public issue**. Use GitHub's [private vulnerability reporting](https://github.com/Atharvabagul84/Chisel/security/advisories/new). Include what you found, how to reproduce it and the expected impact. You'll get a reply within 7 days.

## Scope
- In scope: the Next.js app, its API routes, the Supabase migrations (RLS policies and RPCs), and the hosted-demo limits.
- Please don't run load tests against the hosted preview, try to exhaust its demo limits, or access workspaces that aren't yours.

## Handling secrets
- Provider keys (`ANTHROPIC_API_KEY`, `GROQ_API_KEY`), Upstash tokens and the visitor salt are server-only and never use the `NEXT_PUBLIC_` prefix.
- The app uses only a publishable Supabase key; a service-role key must never appear in code, env files or the browser.
- Secret scanning and push protection are enabled on this repository.
